"""Bounded asyncio WorkerPool с timeout и controlled deterministic fallback."""

from __future__ import annotations

import asyncio

from ..models import WorkerJob, WorkerResult
from .client import ContextWorkerBackend


class WorkerPool:
    """Фактическая concurrency равна min(configured, jobs)."""

    def __init__(
        self, backend: ContextWorkerBackend, max_concurrency: int = 4, timeout_seconds: float = 60.0
    ) -> None:
        if max_concurrency <= 0:
            raise ValueError("max_concurrency должен быть положительным")
        self.backend = backend
        self.max_concurrency = max_concurrency
        self.timeout_seconds = timeout_seconds
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self._closed = False

    async def _run_one(self, job: WorkerJob) -> WorkerResult:
        async with self.semaphore:
            if self._closed:
                return WorkerResult(
                    job_id=job.id, channel=job.channel, status="error", reason="worker pool closed"
                )
            try:
                return await asyncio.wait_for(
                    self.backend.execute(job), timeout=self.timeout_seconds
                )
            except asyncio.TimeoutError:
                return WorkerResult(
                    job_id=job.id,
                    channel=job.channel,
                    status="timeout",
                    observed=[job.content[:2000]],
                    reason="worker timeout; deterministic representation retained",
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                return WorkerResult(
                    job_id=job.id,
                    channel=job.channel,
                    status="error",
                    observed=[job.content[:2000]],
                    reason=f"worker failure: {type(exc).__name__}",
                )

    async def map(self, jobs: list[WorkerJob]) -> list[WorkerResult]:
        if not jobs:
            return []
        return list(await asyncio.gather(*(self._run_one(job) for job in jobs)))

    async def close(self) -> None:
        self._closed = True
