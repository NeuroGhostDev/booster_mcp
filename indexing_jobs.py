"""Наблюдаемые bounded jobs для долгой индексации репозиториев."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

TERMINAL_STATUSES = frozenset({"cancelled", "completed", "failed", "superseded"})
ACTIVE_STATUSES = frozenset({"queued", "running", "cancelling"})


class IndexJobManager:
    """Хранит job state отдельно от тяжёлого index state.

    ``records`` остаётся внешним словарём для обратной совместимости с legacy
    tools и тестами. Все операции поднимают только короткий metadata lock; сам
    worker никогда не вызывается под этим lock.
    """

    def __init__(
        self,
        records: dict[str, dict[str, Any]],
        lock: threading.RLock,
    ) -> None:
        self.records = records
        self.lock = lock
        self._cancel_events: dict[str, threading.Event] = {}
        self._conditions: dict[str, threading.Condition] = {}
        self._repo_by_job: dict[str, str] = {}

    def _condition(self, job_id: str) -> threading.Condition:
        condition = self._conditions.get(job_id)
        if condition is None:
            condition = threading.Condition(self.lock)
            self._conditions[job_id] = condition
        return condition

    @staticmethod
    def _now() -> float:
        return time.monotonic()

    @staticmethod
    def _iso_now() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()

    def _notify(self, job_id: str) -> None:
        condition = self._conditions.get(job_id)
        if condition is not None:
            condition.notify_all()

    def start(
        self,
        repo: str,
        *,
        reason: str,
        task_id: str | None,
        worker: Callable[[str, str, threading.Event], None],
    ) -> tuple[dict[str, Any], bool]:
        """Создаёт job и запускает worker вне metadata lock."""
        with self.lock:
            current = self.records.get(repo)
            if current and current.get("status") in ACTIVE_STATUSES:
                current["rerun_requested"] = True
                current["rerun_reason"] = reason
                if task_id is not None:
                    current["rerun_task_id"] = task_id
                current["updated_at_utc"] = self._iso_now()
                self._notify(str(current.get("job_id", "")))
                return dict(current), False

            job_id = f"idx_{uuid.uuid4().hex}"
            monotonic = self._now()
            record: dict[str, Any] = {
                "job_id": job_id,
                "repository": repo,
                "status": "queued",
                "phase": "scan",
                "processed": 0,
                "total": None,
                "unit": "files",
                "percent": 0.0,
                "queued_at_utc": self._iso_now(),
                "started_at_utc": None,
                "completed_at_utc": None,
                "elapsed_seconds": 0.0,
                "eta_seconds": None,
                "last_progress_at": self._iso_now(),
                "generation_id": None,
                "base_generation_id": None,
                "stale": False,
                "stale_reasons": [],
                "cancel_requested": False,
                "reason": reason,
                "task_id": task_id,
                "error": None,
                "traceback": None,
                "_started_monotonic": monotonic,
            }
            self.records[repo] = record
            self._repo_by_job[job_id] = repo
            cancel_event = threading.Event()
            self._cancel_events[job_id] = cancel_event
            self._condition(job_id)

        thread = threading.Thread(
            target=self._run,
            args=(repo, job_id, cancel_event, worker),
            daemon=True,
            name=f"booster-index-{repo.rsplit('\\', 1)[-1] or 'repo'}",
        )
        thread.start()
        return dict(record), True

    def _run(
        self,
        repo: str,
        job_id: str,
        cancel_event: threading.Event,
        worker: Callable[[str, str, threading.Event], None],
    ) -> None:
        try:
            worker(repo, job_id, cancel_event)
        except Exception as exc:  # pragma: no cover - defensive worker boundary
            self.update(
                repo,
                job_id=job_id,
                status="failed",
                error=str(exc),
                completed_at_utc=self._iso_now(),
            )

    def update(self, repo: str, *, job_id: str | None = None, **updates: Any) -> dict[str, Any]:
        with self.lock:
            record = self.records.setdefault(repo, {})
            if job_id is not None and record.get("job_id") != job_id:
                return dict(record)
            record.update(updates)
            started = record.get("_started_monotonic")
            if isinstance(started, (int, float)):
                elapsed = max(0.0, self._now() - started)
                record["elapsed_seconds"] = round(elapsed, 6)
                total = record.get("total")
                processed = record.get("processed")
                if isinstance(total, int) and total > 0 and isinstance(processed, int):
                    record["percent"] = round(min(100.0, processed * 100 / total), 2)
                    if processed > 0 and elapsed > 0 and processed < total:
                        record["eta_seconds"] = round(elapsed * (total - processed) / processed, 3)
                    elif processed >= total:
                        record["eta_seconds"] = 0.0
            record["updated_at_utc"] = self._iso_now()
            active_job_id = str(record.get("job_id", job_id or ""))
            self._notify(active_job_id)
            return dict(record)

    def progress(
        self,
        repo: str,
        job_id: str,
        *,
        phase: str,
        processed: int,
        total: int | None,
        generation_id: str | None = None,
        base_generation_id: str | None = None,
    ) -> dict[str, Any]:
        return self.update(
            repo,
            job_id=job_id,
            status="cancelling" if self.is_cancel_requested(job_id) else "running",
            phase=phase,
            processed=max(0, processed),
            total=total,
            generation_id=generation_id,
            base_generation_id=base_generation_id,
            last_progress_at=self._iso_now(),
            started_at_utc=self._started_at(repo),
        )

    def _started_at(self, repo: str) -> str:
        value = self.records.get(repo, {}).get("started_at_utc")
        return value or self._iso_now()

    def mark_running(self, repo: str, job_id: str) -> dict[str, Any]:
        with self.lock:
            record = self.records.get(repo, {})
            if record.get("job_id") != job_id:
                return dict(record)
            if record.get("started_at_utc") is None:
                record["started_at_utc"] = self._iso_now()
                record["_started_monotonic"] = self._now()
        return self.update(repo, job_id=job_id, status="running")

    def finish(self, repo: str, job_id: str, status: str, **updates: Any) -> dict[str, Any]:
        if status not in TERMINAL_STATUSES:
            raise ValueError(f"unsupported terminal status: {status}")
        updates.setdefault("completed_at_utc", self._iso_now())
        updates.setdefault("eta_seconds", 0.0)
        result = self.update(repo, job_id=job_id, status=status, **updates)
        with self.lock:
            self._notify(job_id)
        return result

    def is_cancel_requested(self, job_id: str) -> bool:
        event = self._cancel_events.get(job_id)
        return bool(event and event.is_set())

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self.lock:
            repo = self._repo_by_job.get(job_id)
            if repo is None:
                return None
            record = self.records.get(repo, {})
            if record.get("job_id") != job_id:
                return dict(record)
            status = record.get("status")
            if status in TERMINAL_STATUSES:
                return dict(record)
            event = self._cancel_events.setdefault(job_id, threading.Event())
            event.set()
            record["cancel_requested"] = True
            record["status"] = "cancelling"
            record["updated_at_utc"] = self._iso_now()
            self._notify(job_id)
            return dict(record)

    def get(self, *, repo: str | None = None, job_id: str | None = None) -> dict[str, Any] | None:
        with self.lock:
            if job_id is not None:
                repo = self._repo_by_job.get(job_id, repo)
            if repo is None:
                return None
            record = self.records.get(repo)
            if record is None or (job_id is not None and record.get("job_id") != job_id):
                return None
            return {key: value for key, value in record.items() if not key.startswith("_")}

    def wait(self, job_id: str, timeout_seconds: float) -> dict[str, Any] | None:
        deadline = self._now() + max(0.0, timeout_seconds)
        with self.lock:
            repo = self._repo_by_job.get(job_id)
            if repo is None:
                for candidate_repo, record in self.records.items():
                    if record.get("job_id") == job_id:
                        repo = candidate_repo
                        self._repo_by_job[job_id] = candidate_repo
                        break
            if repo is None:
                return None
            condition = self._condition(job_id)
            while True:
                record = self.records.get(repo, {})
                if record.get("status") in TERMINAL_STATUSES:
                    return self.get(job_id=job_id)
                remaining = deadline - self._now()
                if remaining <= 0:
                    value = self.get(job_id=job_id) or {}
                    value["timed_out"] = True
                    return value
                condition.wait(timeout=remaining)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self.lock:
            return {
                repo: {key: value for key, value in record.items() if not key.startswith("_")}
                for repo, record in self.records.items()
            }
