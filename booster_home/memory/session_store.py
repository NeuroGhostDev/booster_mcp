"""Session resolution, timeline и TTL cleanup без mutable current_session."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from file_lock import cross_process_file_lock

from .models import Session, TimelineEvent, WorkingSet


class SessionStore:
    """Изолирует metadata/timeline каждой logical session."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.sessions_root = self.root / "sessions"
        self._locks: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def _lock(self, session_id: str) -> AsyncIterator[None]:
        safe_id = self._safe_id(session_id)
        local_lock = self._locks.setdefault(safe_id, asyncio.Lock())
        async with local_lock:
            with cross_process_file_lock(self._path(safe_id) / ".session.lock"):
                yield

    @staticmethod
    def _safe_id(value: str) -> str:
        value = value.strip()
        if re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value):
            return value
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]

    def _path(self, session_id: str) -> Path:
        path = (self.sessions_root / self._safe_id(session_id)).resolve()
        if self.sessions_root not in path.parents:
            raise ValueError("session path выходит за пределы storage")
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _atomic_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        try:
            with open(fd, "w", encoding="utf-8", closefd=True) as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2, default=str)
                stream.flush()
            Path(temp_name).replace(path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise

    def resolve_id(
        self,
        explicit: str | None = None,
        conversation_metadata: dict[str, Any] | None = None,
        client_metadata: dict[str, Any] | None = None,
    ) -> str:
        """Применяет header -> conversation metadata -> client metadata -> fallback."""
        candidates = [
            explicit,
            *(
                conversation_metadata.get(key)
                for key in ("session_id", "conversation_id")
                if conversation_metadata
            ),
            *(
                client_metadata.get(key)
                for key in ("session_id", "conversation_id", "client_id")
                if client_metadata
            ),
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return self._safe_id(candidate)
        return "anonymous"

    async def resolve_session(
        self,
        explicit: str | None = None,
        conversation_metadata: dict[str, Any] | None = None,
        client_metadata: dict[str, Any] | None = None,
    ) -> Session:
        """Разрешает stable id и гарантирует metadata directory."""
        session_id = self.resolve_id(explicit, conversation_metadata, client_metadata)
        metadata = {**(conversation_metadata or {}), **(client_metadata or {})}
        return await self.get_or_create(session_id, metadata=metadata)

    async def get_or_create(
        self, session_id: str, metadata: dict[str, Any] | None = None
    ) -> Session:
        safe_id = self._safe_id(session_id)
        path = self._path(safe_id) / "session.json"
        async with self._lock(safe_id):
            if path.is_file():
                try:
                    return Session.model_validate_json(path.read_text(encoding="utf-8"))
                except ValueError:
                    # Повреждённая metadata не должна смешиваться с другой session.
                    raise IOError(f"session metadata повреждена: {safe_id}")
            session = Session(session_id=safe_id, metadata=metadata or {})
            self._atomic_json(path, session.model_dump(mode="json"))
            self._atomic_json(
                self._path(safe_id) / "working_set.json",
                WorkingSet(session_id=safe_id).model_dump(mode="json"),
            )
            return session

    async def context(self, session_id: str) -> dict[str, Any]:
        session = await self.get_or_create(session_id)
        working_path = self._path(session.session_id) / "working_set.json"
        working: dict[str, Any] = {}
        if working_path.is_file():
            working = json.loads(working_path.read_text(encoding="utf-8"))
        events = await self.read_events(session.session_id, limit=20)
        return {"session": session, "working_set": working, "recent_events": events}

    async def append_event(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        request_id: str | None = None,
    ) -> TimelineEvent:
        safe_id = self._safe_id(session_id)
        await self.get_or_create(safe_id)
        async with self._lock(safe_id):
            timeline = self._path(safe_id) / "timeline.jsonl"
            seq = 1
            if timeline.is_file():
                with timeline.open("r", encoding="utf-8") as stream:
                    seq = sum(1 for _ in stream) + 1
            event = TimelineEvent(
                seq=seq,
                type=event_type,
                session_id=safe_id,
                request_id=request_id,
                payload=payload or {},
            )
            with timeline.open("a", encoding="utf-8") as stream:
                stream.write(event.model_dump_json() + "\n")
            metadata_path = self._path(safe_id) / "session.json"
            session = Session.model_validate_json(metadata_path.read_text(encoding="utf-8"))
            session.updated_at = datetime.now(timezone.utc)
            self._atomic_json(metadata_path, session.model_dump(mode="json"))
            return event

    async def read_events(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        path = self._path(session_id) / "timeline.jsonl"
        if not path.is_file():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        result: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return result

    async def update_working_set(self, working_set: WorkingSet) -> WorkingSet:
        safe_id = self._safe_id(working_set.session_id)
        await self.get_or_create(safe_id)
        async with self._lock(safe_id):
            self._atomic_json(
                self._path(safe_id) / "working_set.json", working_set.model_dump(mode="json")
            )
        return working_set

    async def get_working_set(self, session_id: str) -> WorkingSet:
        await self.get_or_create(session_id)
        path = self._path(session_id) / "working_set.json"
        return WorkingSet.model_validate_json(path.read_text(encoding="utf-8"))

    async def set_active(self, session_id: str, active: bool) -> Session:
        """Обновляет active-флаг для защиты сессии от maintenance cleanup."""
        safe_id = self._safe_id(session_id)
        await self.get_or_create(safe_id)
        async with self._lock(safe_id):
            path = self._path(safe_id) / "session.json"
            session = Session.model_validate_json(path.read_text(encoding="utf-8"))
            session.active = active
            session.updated_at = datetime.now(timezone.utc)
            self._atomic_json(path, session.model_dump(mode="json"))
            return session

    async def list_sessions(self) -> list[Session]:
        self.sessions_root.mkdir(parents=True, exist_ok=True)
        result: list[Session] = []
        for path in sorted(self.sessions_root.glob("*/session.json")):
            try:
                result.append(Session.model_validate_json(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return result

    async def delete(self, session_id: str) -> bool:
        safe_id = self._safe_id(session_id)
        path = (self.sessions_root / safe_id).resolve()
        if self.sessions_root not in path.parents:
            raise ValueError("session path выходит за пределы storage")
        if not path.exists():
            return False
        async with self._lock(safe_id):
            import shutil

            shutil.rmtree(path)
        return True

    async def cleanup(self, max_age_days: int, *, active_ids: set[str] | None = None) -> list[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        active = {self._safe_id(item) for item in (active_ids or set())}
        removed: list[str] = []
        for session in await self.list_sessions():
            if session.session_id in active:
                continue
            updated = session.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if session.active and updated >= cutoff:
                continue
            if updated < cutoff and await self.delete(session.session_id):
                removed.append(session.session_id)
        return removed
