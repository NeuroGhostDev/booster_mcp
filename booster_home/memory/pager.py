"""Pager с invariant persist-before-evict."""

from __future__ import annotations

from ..models import ContextBlock
from .artifact_store import ArtifactMetadata, ArtifactStore


class ContextIntegrityError(RuntimeError):
    """Нельзя вытеснить block, пока raw persistence не подтверждена."""


class MemoryPager:
    """Сохраняет вытесняемые blocks и возвращает artifact references."""

    def __init__(self, artifacts: ArtifactStore, enabled: bool = True) -> None:
        self.artifacts = artifacts
        self.enabled = enabled

    async def persist_before_evict(
        self,
        session_id: str,
        block: ContextBlock,
        *,
        artifact_type: str | None = None,
        task_id: str | None = None,
    ) -> ArtifactMetadata:
        if not self.enabled:
            raise ContextIntegrityError(
                "raw artifact persistence отключена: eviction при нехватке budget запрещён"
            )
        try:
            return await self.artifacts.store(
                session_id,
                block.content,
                artifact_type=artifact_type or block.category.value,
                source=block.source,
                task_id=task_id,
            )
        except Exception as exc:
            raise ContextIntegrityError("raw artifact не удалось надёжно сохранить") from exc

    async def retrieve(
        self, session_id: str, artifact_ref: str, fragment: dict[str, int] | None = None
    ) -> str:
        if fragment:
            return await self.artifacts.retrieve_fragment(session_id, artifact_ref, **fragment)
        return str(await self.artifacts.retrieve(session_id, artifact_ref))
