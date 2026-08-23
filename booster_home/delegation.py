"""Local delegation API поверх того же WorkerPool и router."""

from __future__ import annotations

from typing import Any

from .models import WorkerJob
from .routing import ModelRouter
from .workers.pool import WorkerPool


class LocalDelegator:
    """Собирает bounded task context и не создаёт отдельный HTTP client."""

    def __init__(self, pool: WorkerPool, router: ModelRouter | None = None) -> None:
        self.pool = pool
        self.router = router

    async def delegate_local(
        self,
        task: str,
        *,
        role: str = "worker",
        model: str | None = None,
        context_policy: str = "auto",
        max_output_tokens: int | None = None,
        repo: str | None = None,
        context: str = "",
    ) -> dict[str, Any]:
        selected = model
        if selected is None and self.router is not None:
            selected = self.router.choose(role).model
        job = WorkerJob(
            channel=role,
            content=f"TASK\n{task}\nCONTEXT\n{context[:20000]}",
            task=f"delegate:{context_policy}",
            model=selected,
            metadata={"repo": repo, "max_output_tokens": max_output_tokens},
        )
        result = (await self.pool.map([job]))[0]
        return result.model_dump()
