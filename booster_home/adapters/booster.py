"""Typed bridge к одному существующему RepoIndexer/CognitiveRuntime."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import ContextBlock, ContextCategory, Priority, SessionContext


@dataclass(slots=True)
class EnrichmentResult:
    """Bounded targeted retrieval result."""

    blocks: list[ContextBlock] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BoosterWorldModelAdapter:
    """Использует legacy index/graphs/memory, не создавая второй vector DB."""

    def __init__(
        self,
        indexer: Any | None = None,
        cognitive_runtime: Any | None = None,
        repo_map: Any | None = None,
        *,
        repo: Path | None = None,
    ) -> None:
        self.indexer = indexer
        self.cognitive_runtime = cognitive_runtime
        self.repo_map = repo_map
        self.repo = repo.expanduser().resolve() if repo else None

    async def enrich(
        self,
        task: str,
        session: SessionContext,
        *,
        max_tokens: int = 2048,
    ) -> EnrichmentResult:
        """Делает только top-k retrieval и не вызывает полный RepoMap на request."""
        if not task.strip():
            return EnrichmentResult()
        return await asyncio.to_thread(self._enrich_sync, task, session, max_tokens)

    def _enrich_sync(self, task: str, session: SessionContext, max_tokens: int) -> EnrichmentResult:
        blocks: list[ContextBlock] = []
        warnings: list[str] = []
        repo = str(self.repo) if self.repo else None
        active_files = list(session.working_set.get("files", []))[:5]
        query = task + (" " + " ".join(active_files) if active_files else "")

        if self.indexer is not None:
            try:
                results = self.indexer.hybrid_search(query, k=5)
            except Exception as exc:
                warnings.append(f"hybrid retrieval unavailable: {type(exc).__name__}")
                results = []
            for index, item in enumerate(results[:5]):
                if not isinstance(item, dict):
                    continue
                content = item.get("content") or item.get("text") or item.get("code")
                if not isinstance(content, str) or not content.strip():
                    continue
                block = ContextBlock(
                    source="repo_index",
                    category=ContextCategory.REPO_CONTEXT,
                    content=content[: max(1000, max_tokens * 4)],
                    priority=Priority.P2,
                    relevance=max(0.0, 1.0 - index * 0.12),
                    recoverable=True,
                    metadata={"untrusted": True, "retrieval_rank": index, "file": item.get("file")},
                )
                blocks.append(block)

        if self.cognitive_runtime is not None:
            target = _infer_target(task)
            if target:
                try:
                    impact = self.cognitive_runtime.impact_analysis(target, repo=repo, max_depth=1)
                    compact = json.dumps(impact, ensure_ascii=False, sort_keys=True)[
                        : max(1000, max_tokens * 2)
                    ]
                    blocks.append(
                        ContextBlock(
                            source="impact_analysis",
                            category=ContextCategory.REPO_CONTEXT,
                            content=f"targeted impact for {target}:\n{compact}",
                            priority=Priority.P2,
                            relevance=0.9,
                            metadata={"untrusted": True, "target": target},
                        )
                    )
                except Exception as exc:
                    warnings.append(f"impact analysis unavailable: {type(exc).__name__}")
        return EnrichmentResult(blocks=blocks[:8], warnings=warnings)


def _infer_target(task: str) -> str | None:
    for token in task.replace("/", " ").split():
        cleaned = token.strip("`.,:()[]{}")
        if "." in cleaned or (cleaned and cleaned[0].isupper()):
            return cleaned
    return None
