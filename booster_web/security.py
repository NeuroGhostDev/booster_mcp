"""Repository allowlisting and path containment for the web surface."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import threading
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class RateLimitExceeded(RuntimeError):
    """Raised when a client exceeds the browser gateway request budget."""


class OperationTimedOut(RuntimeError):
    """Raised when a guarded read-only operation exceeds its deadline."""


@dataclass(frozen=True)
class WebSecuritySettings:
    """Fail-closed resource limits for the public browser boundary."""

    max_concurrent: int = 4
    timeout_seconds: float = 10.0
    rate_limit_requests: int = 60
    rate_limit_window_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not 1 <= self.max_concurrent <= 4:
            raise ValueError("max_concurrent must be between 1 and 4")
        if not 0 < self.timeout_seconds <= 10:
            raise ValueError("timeout_seconds must be between 0 and 10")
        if self.rate_limit_requests < 1:
            raise ValueError("rate_limit_requests must be positive")
        if self.rate_limit_window_seconds <= 0:
            raise ValueError("rate_limit_window_seconds must be positive")

    @classmethod
    def from_env(cls) -> "WebSecuritySettings":
        """Read only bounded operator settings; invalid values use safe defaults."""

        def read_int(name: str, default: int, minimum: int, maximum: int) -> int:
            try:
                value = int(os.getenv(name, str(default)))
            except (TypeError, ValueError):
                return default
            return min(maximum, max(minimum, value))

        def read_float(name: str, default: float, minimum: float, maximum: float) -> float:
            try:
                value = float(os.getenv(name, str(default)))
            except (TypeError, ValueError):
                return default
            return min(maximum, max(minimum, value))

        return cls(
            max_concurrent=read_int("BOOSTER_WEB_MAX_CONCURRENT", 4, 1, 4),
            timeout_seconds=read_float("BOOSTER_WEB_TIMEOUT_SECONDS", 10.0, 0.1, 10.0),
            rate_limit_requests=read_int("BOOSTER_WEB_RATE_LIMIT_REQUESTS", 60, 1, 600),
            rate_limit_window_seconds=read_float(
                "BOOSTER_WEB_RATE_LIMIT_WINDOW_SECONDS", 60.0, 1.0, 3600.0
            ),
        )


class _SlidingWindowLimiter:
    def __init__(self, maximum: int, window_seconds: float) -> None:
        self.maximum = maximum
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            events = self._events.setdefault(key, deque())
            cutoff = now - self.window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.maximum:
                return False
            events.append(now)
            if len(self._events) > 1024:
                self._events = {
                    item: values
                    for item, values in self._events.items()
                    if values and values[-1] > cutoff
                }
            return True


class WebRequestGuard:
    """Shared rate/concurrency/deadline guard for browser-facing operations."""

    def __init__(self, settings: WebSecuritySettings | None = None) -> None:
        self.settings = settings or WebSecuritySettings.from_env()
        self._limiter = _SlidingWindowLimiter(
            self.settings.rate_limit_requests,
            self.settings.rate_limit_window_seconds,
        )
        self._semaphore = asyncio.Semaphore(self.settings.max_concurrent)

    @staticmethod
    def client_key(client_host: str | None) -> str:
        return client_host or "unknown"

    def check_rate(self, client_host: str | None) -> None:
        if not self._limiter.allow(self.client_key(client_host)):
            raise RateLimitExceeded("Request rate limit exceeded")

    async def run(self, client_host: str | None, operation: Any, *args: Any) -> Any:
        self.check_rate(client_host)
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=0.05)
        except TimeoutError as exc:
            raise RateLimitExceeded("Too many concurrent operations") from exc

        worker = asyncio.create_task(asyncio.to_thread(operation, *args))
        release_on_worker_done = False
        try:
            return await asyncio.wait_for(
                asyncio.shield(worker), timeout=self.settings.timeout_seconds
            )
        except TimeoutError as exc:
            release_on_worker_done = True
            raise OperationTimedOut("Operation timed out") from exc
        except asyncio.CancelledError:
            release_on_worker_done = True
            raise
        finally:
            if release_on_worker_done:
                worker.add_done_callback(lambda _task: self._semaphore.release())
            else:
                self._semaphore.release()


class RepositoryAllowlist:
    """Maps safe logical repository IDs to known local roots.

    The browser never supplies a root path. Explicit mappings are preferred;
    registry records are only used to derive stable display IDs when no mapping
    is provided by the application.
    """

    def __init__(
        self,
        repositories: Mapping[str, str | Path] | None = None,
        *,
        registry: Any | None = None,
        default_repo_id: str | None = None,
    ) -> None:
        values: dict[str, Path] = {}
        if repositories is not None:
            for repo_id, root in repositories.items():
                self._validate_repo_id(repo_id)
                values[repo_id] = self._normalize_root(root)
        elif registry is not None:
            records = self._registry_records(registry)
            for record in records:
                root_value = record.get("repository")
                if not isinstance(root_value, str) or not root_value:
                    continue
                root = self._normalize_root(root_value)
                requested_id = record.get("repo_id") or record.get("id")
                repo_id = self._safe_registry_id(requested_id, root)
                if repo_id in values and values[repo_id] != root:
                    suffix = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:8]
                    repo_id = f"{repo_id[:55]}-{suffix}"
                values[repo_id] = root

        self._repositories = values
        if default_repo_id is not None:
            self._validate_repo_id(default_repo_id)
            if default_repo_id not in values:
                raise ValueError(f"Unknown default repository ID: {default_repo_id}")
        self.default_repo_id = default_repo_id or next(iter(values), None)

    @staticmethod
    def _normalize_root(root: str | Path) -> Path:
        if not isinstance(root, (str, Path)):
            raise ValueError("repository root must be a path")
        value = str(root)
        if "\x00" in value:
            raise ValueError("repository root contains a null byte")
        return Path(root).expanduser().resolve()

    @staticmethod
    def _validate_repo_id(repo_id: str) -> None:
        if not isinstance(repo_id, str) or not REPO_ID_PATTERN.fullmatch(repo_id):
            raise ValueError("repo_id must contain only letters, digits, '.', '_' or '-'")

    @classmethod
    def _safe_registry_id(cls, requested_id: Any, root: Path) -> str:
        candidate = requested_id if isinstance(requested_id, str) else root.name
        candidate = re.sub(r"[^A-Za-z0-9._-]+", "-", candidate).strip("-._")
        if not candidate:
            candidate = "repo"
        if not candidate[0].isalnum():
            candidate = f"repo-{candidate}"
        return candidate[:64]

    @staticmethod
    def _registry_records(registry: Any) -> list[dict[str, Any]]:
        list_records = getattr(registry, "list_records", None)
        if callable(list_records):
            records = list_records()
            if not isinstance(records, list):
                return []
            return [record for record in records if isinstance(record, dict)]
        list_repos = getattr(registry, "list_repos", None)
        if not callable(list_repos):
            return []
        repos = list_repos()
        if not isinstance(repos, list):
            return []
        return [{"repository": value} for value in repos if isinstance(value, str)]

    @property
    def repository_ids(self) -> tuple[str, ...]:
        return tuple(self._repositories)

    def as_mapping(self) -> dict[str, Path]:
        return dict(self._repositories)

    def resolve_repo(self, repo_id: str) -> Path:
        self._validate_repo_id(repo_id)
        root = self._repositories.get(repo_id)
        if root is None or not root.is_dir():
            raise KeyError(repo_id)
        return root

    def resolve_relative_path(self, repo_id: str, relative_path: str) -> Path:
        """Resolve a repository-relative path without allowing traversal."""

        root = self.resolve_repo(repo_id)
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("relative_path must not be blank")
        if "\x00" in relative_path:
            raise ValueError("relative_path contains a null byte")
        requested = Path(relative_path)
        if requested.is_absolute():
            raise ValueError("relative_path must be relative")
        resolved = (root / requested).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError("relative_path escapes repository root")
        return resolved
