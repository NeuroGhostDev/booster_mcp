from __future__ import annotations

import asyncio

import pytest

from booster_home.models import WorkerJob, WorkerResult
from booster_home.workers.pool import WorkerPool


class SlowBackend:
    def __init__(self) -> None:
        self.active = 0
        self.maximum = 0

    async def execute(self, job: WorkerJob) -> WorkerResult:
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        return WorkerResult(job_id=job.id, channel=job.channel, status="success", summary="ok")


@pytest.mark.asyncio
async def test_worker_pool_is_bounded() -> None:
    backend = SlowBackend()
    pool = WorkerPool(backend, max_concurrency=2, timeout_seconds=1)
    results = await pool.map([WorkerJob(channel="x", content=str(index)) for index in range(5)])
    assert len(results) == 5
    assert backend.maximum <= 2
