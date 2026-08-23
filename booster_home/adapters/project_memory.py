"""Разделение session memory и legacy project memory с безопасным promotion."""

from __future__ import annotations

import asyncio
from typing import Any

from ..memory.models import Decision
from ..models import ContextBlock, ContextCategory, Priority


class ProjectMemoryAdapter:
    """Читает existing CognitiveRuntime memory и продвигает только validated decisions."""

    def __init__(self, cognitive_runtime: Any | None = None, repo: str | None = None) -> None:
        self.cognitive_runtime = cognitive_runtime
        self.repo = repo

    async def recall(self, query: str, limit: int = 8) -> list[ContextBlock]:
        if self.cognitive_runtime is None:
            return []
        result = await asyncio.to_thread(
            self.cognitive_runtime.project_memory_recall, query=query, repo=self.repo, limit=limit
        )
        blocks: list[ContextBlock] = []
        for index, fact in enumerate(result.get("facts", []) if isinstance(result, dict) else []):
            if not isinstance(fact, dict) or not fact.get("fact"):
                continue
            blocks.append(
                ContextBlock(
                    source="project_memory",
                    category=ContextCategory.PROJECT_MEMORY,
                    content=str(fact["fact"]),
                    priority=Priority.P2,
                    relevance=max(0.0, 0.9 - index * 0.1),
                    metadata={
                        "untrusted": True,
                        "fact_id": fact.get("id"),
                        "category": fact.get("category"),
                    },
                )
            )
        return blocks

    async def promote_decision(self, decision: Decision) -> dict[str, Any]:
        """Обычные сообщения и непроверенные inference не попадают в project memory."""
        if self.cognitive_runtime is None:
            return {"promoted": False, "reason": "project memory adapter unavailable"}
        if (
            decision.status != "validated"
            or not decision.evidence
            or decision.rejected
            or decision.superseded
        ):
            return {"promoted": False, "reason": "decision lacks validated stable evidence"}
        return await asyncio.to_thread(
            self.cognitive_runtime.remember_project_fact,
            category="decision",
            fact=decision.statement,
            confidence=1.0,
            source=decision.source,
            repo=self.repo,
        )
