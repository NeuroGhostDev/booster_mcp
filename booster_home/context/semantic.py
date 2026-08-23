"""Partitioned semantic processing поверх общего WorkerPool."""

from __future__ import annotations

from collections import defaultdict

from ..models import ContextBlock, ContextCategory, ModelProfile, WorkerJob, WorkerResult
from ..workers.pool import WorkerPool

SEMANTIC_CHANNELS = {
    ContextCategory.TERMINAL: "terminal",
    ContextCategory.DIAGNOSTIC: "diagnostics",
    ContextCategory.TEST_OUTPUT: "tests",
    ContextCategory.BUILD_OUTPUT: "build",
    ContextCategory.TOOL_RESULT: "tool_results",
    ContextCategory.ASSISTANT_RESPONSE: "conversation",
    ContextCategory.DIFF: "diff",
    ContextCategory.SOURCE_CODE: "repo_snippets",
}


class SemanticProcessor:
    """Не отправляет worker весь request: блоки partitioned и bounded."""

    def __init__(self, pool: WorkerPool | None, max_chars_per_job: int = 12_000) -> None:
        self.pool = pool
        self.max_chars_per_job = max(1000, max_chars_per_job)

    def build_jobs(
        self, blocks: list[ContextBlock], task: str, model: ModelProfile
    ) -> list[WorkerJob]:
        grouped: defaultdict[str, list[str]] = defaultdict(list)
        for block in blocks:
            channel = SEMANTIC_CHANNELS.get(block.category)
            if channel is None or block.priority <= 1:
                continue
            grouped[channel].append(block.content)
        jobs: list[WorkerJob] = []
        for channel, contents in grouped.items():
            current = ""
            for content in contents:
                if current and len(current) + len(content) + 1 > self.max_chars_per_job:
                    jobs.append(
                        WorkerJob(channel=channel, content=current, task=task, model=model.id)
                    )
                    current = ""
                current += ("\n" if current else "") + content
            if current:
                jobs.append(WorkerJob(channel=channel, content=current, task=task, model=model.id))
        return jobs

    async def process(
        self, blocks: list[ContextBlock], task: str, model: ModelProfile
    ) -> list[WorkerResult]:
        if self.pool is None:
            return []
        jobs = self.build_jobs(blocks, task, model)
        return await self.pool.map(jobs)
