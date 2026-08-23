"""Безопасное чтение research state и файлов научного проекта."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterable

from .models import CheckpointRecord

IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    "target",
    ".agents/booster/runtime",
}

CHECKPOINT_EXTENSIONS = {".pt", ".pth", ".ckpt", ".safetensors", ".bin"}
TEXT_EXTENSIONS = {
    ".py",
    ".rs",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".md",
    ".txt",
    ".log",
    ".csv",
}


class ResearchInputError(ValueError):
    """Ошибка входных данных research tool."""


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _token_count(value: str) -> int:
    return max(1, (len(value) + 3) // 4) if value else 0


def _normalise_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _walk_values(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from _walk_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_values(item)


def _find_value(value: Any, aliases: set[str]) -> Any:
    for key, item in _walk_values(value):
        if _normalise_key(key) in aliases:
            return item
    return None


class ResearchStateStore:
    """Читает state/metrics без исполнения содержимого как конфигурации."""

    def __init__(self, root: Path, *, max_files: int = 2000) -> None:
        self.root = root.expanduser().resolve()
        if not self.root.exists() or not self.root.is_dir():
            raise ResearchInputError(f"research root не найден: {self.root}")
        self.max_files = max(1, min(max_files, 10000))
        self._lock = threading.RLock()

    def resolve_path(self, value: str | Path | None, *, must_exist: bool = True) -> Path:
        path = self.root if value is None else Path(value).expanduser()
        if not path.is_absolute():
            path = self.root / path
        resolved = path.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ResearchInputError("путь research artifact выходит за пределы root") from exc
        if must_exist and not resolved.exists():
            raise ResearchInputError(f"research artifact не найден: {resolved}")
        return resolved

    @staticmethod
    def is_checkpoint(path: Path) -> bool:
        return path.suffix.lower() in CHECKPOINT_EXTENSIONS

    def _ignored(self, path: Path) -> bool:
        try:
            relative = path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return True
        parts = relative.split("/")
        for index, part in enumerate(parts[:-1]):
            if part in IGNORED_DIRECTORIES:
                return True
            if "/".join(parts[index : index + 3]) == ".agents/booster/runtime":
                return True
        return False

    def iter_files(self, patterns: list[str] | None = None) -> list[tuple[Path, bool]]:
        """Возвращает bounded список файлов и metadata-only flag."""
        selected: dict[Path, bool] = {}
        raw_patterns = patterns or ["**/*"]
        for raw_pattern in raw_patterns:
            pattern = str(raw_pattern).strip()
            metadata_only = False
            if pattern.lower().endswith(" metadata only"):
                metadata_only = True
                pattern = pattern[: -len(" metadata only")].rstrip()
            if not pattern:
                continue
            try:
                candidates = self.root.glob(pattern)
            except (IndexError, NotImplementedError, ValueError) as exc:
                raise ResearchInputError(f"некорректный include pattern: {pattern}") from exc
            for candidate in candidates:
                if not candidate.is_file() or self._ignored(candidate):
                    continue
                resolved = candidate.resolve()
                try:
                    resolved.relative_to(self.root)
                except ValueError:
                    continue
                selected[resolved] = selected.get(resolved, False) or metadata_only
                if len(selected) >= self.max_files:
                    break
            if len(selected) >= self.max_files:
                break
        return [(path, metadata_only) for path, metadata_only in sorted(selected.items())]

    @staticmethod
    def read_text(path: Path, *, max_bytes: int = 128_000) -> tuple[str, bool]:
        size = path.stat().st_size
        truncated = size > max_bytes
        with path.open("rb") as stream:
            if not truncated:
                data = stream.read()
            else:
                half = max_bytes // 2
                first = stream.read(half)
                stream.seek(max(half, size - half))
                last = stream.read(half)
                data = first + b"\n... [truncated] ...\n" + last
        return data.decode("utf-8", errors="replace"), truncated

    @staticmethod
    def _sidecar_candidates(path: Path) -> list[Path]:
        return [
            path.with_suffix(path.suffix + ".json"),
            path.with_suffix(".json"),
            path.with_name(f"{path.stem}_metadata.json"),
            path.with_name(f"{path.stem}.metadata.json"),
        ]

    def checkpoint_metadata(self, path: Path) -> CheckpointRecord:
        """Извлекает только stat и sidecar metadata, не читая checkpoint body."""
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise ResearchInputError(f"не удалось получить stat checkpoint: {path}") from exc
        metadata: dict[str, Any] = {}
        source: Path | None = None
        for candidate in self._sidecar_candidates(path):
            if not candidate.is_file() or self._ignored(candidate):
                continue
            try:
                sidecar_text, _ = self.read_text(candidate, max_bytes=64_000)
                value = json.loads(sidecar_text)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                metadata = value
                source = candidate
                break
        match = re.search(r"(?:step|iter|iteration)[_-]?(\d+)", path.stem, re.IGNORECASE)
        step = _find_value(metadata, {"step", "global_step", "iteration", "iter"})
        if step is None and match:
            step = int(match.group(1))
        try:
            normalized_step = int(step) if step is not None else None
        except (TypeError, ValueError):
            normalized_step = None
        groups = _find_value(metadata, {"trainable_groups", "trainable", "trainable_parameters"})
        if isinstance(groups, str):
            groups = [groups]
        if not isinstance(groups, list):
            groups = []
        metrics = _find_value(metadata, {"metrics", "eval_metrics", "results"})
        if not isinstance(metrics, dict):
            metrics = {}
        return CheckpointRecord(
            path=path.relative_to(self.root).as_posix(),
            filename=path.name,
            size_bytes=size,
            size=size,
            step=normalized_step,
            base_checkpoint=_find_value(metadata, {"base_checkpoint", "base", "base_model"}),
            trainable_groups=[str(item) for item in groups],
            metrics=metrics,
            parent_experiment=_find_value(metadata, {"parent_experiment", "parent_run", "parent"}),
            experiment=_find_value(metadata, {"experiment", "run", "run_id"}),
            status=_find_value(metadata, {"status"}),
            keep=_find_value(metadata, {"keep", "retain"}),
            branch=_find_value(metadata, {"branch", "experiment_branch"}),
            metadata_source=(source.relative_to(self.root).as_posix() if source else None),
        )

    def state_path(self) -> Path:
        return self.root / "research_state.json"

    def load_state(self) -> tuple[dict[str, Any], list[str]]:
        warnings: list[str] = []
        candidates = [self.state_path(), self.root / ".agents" / "booster" / "research_state.json"]
        for path in candidates:
            if not path.is_file():
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                warnings.append(f"state unreadable: {path.name} ({type(exc).__name__})")
                continue
            if isinstance(value, dict):
                return value, warnings
            warnings.append(f"state ignored: {path.name} is not an object")
        return {}, warnings

    @staticmethod
    def _atomic_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2, default=str)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise

    def save_state(self, value: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            payload = dict(value)
            payload["updated_at_utc"] = _utc_now()
            self._atomic_json(self.state_path(), payload)
            return payload

    def update_state(self, update: Any) -> dict[str, Any]:
        with self._lock:
            state, _ = self.load_state()
            updated = update(dict(state))
            if not isinstance(updated, dict):
                raise TypeError("research state update должен вернуть object")
            return self.save_state(updated)

    def memory_files(self) -> list[Path]:
        candidates = [self.root / "memory_bank.md", self.root / "memory-bank.md"]
        memory_dir = self.root / "memory-bank"
        if memory_dir.is_dir():
            candidates.extend(sorted(memory_dir.glob("*.md")))
        return [path for path in candidates if path.is_file() and not self._ignored(path)]

    def metric_files(self) -> list[Path]:
        result: list[Path] = []
        for path, _ in self.iter_files(["**/*metrics*.jsonl", "**/*report*.json"]):
            result.append(path)
        return result

    def fingerprint(self, path: Path) -> str:
        try:
            stat = path.stat()
            value = f"{path}:{stat.st_size}:{stat.st_mtime_ns}"
        except OSError:
            value = str(path)
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


__all__ = [
    "CHECKPOINT_EXTENSIONS",
    "IGNORED_DIRECTORIES",
    "ResearchInputError",
    "ResearchStateStore",
    "TEXT_EXTENSIONS",
    "_token_count",
]
