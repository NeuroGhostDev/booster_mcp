from __future__ import annotations

import pytest

from booster_home.delegation import LocalDelegator
from booster_home.models import WorkerResult
from booster_home.workers.pool import WorkerPool


class Backend:
    async def execute(self, job):
        return WorkerResult(
            job_id=job.id, channel=job.channel, status="success", observed=[job.content]
        )


@pytest.mark.asyncio
async def test_delegation_uses_shared_pool() -> None:
    pool = WorkerPool(Backend(), 1, 1)
    result = await LocalDelegator(pool).delegate_local(
        "check tests", role="tests", context="pytest"
    )
    assert result["status"] == "success"
    await pool.close()
