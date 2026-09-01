"""Полная многоступенчатая Context Compiler pipeline."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..adapters.booster import BoosterWorldModelAdapter
from ..adapters.project_memory import ProjectMemoryAdapter
from ..memory.artifact_store import ArtifactStore
from ..memory.pager import ContextIntegrityError, MemoryPager
from ..models import (
    ChatCompletionRequest,
    CompiledContext,
    ContextBlock,
    ContextCategory,
    ContextOperation,
    ContextPolicy,
    Message,
    ModelProfile,
    Priority,
    SessionContext,
)
from ..workers.pool import WorkerPool
from .budget import ContextBudgetError, ContextBudgetManager
from .classifier import MessageClassifier
from .deterministic import deterministic_normalize
from .packer import ContextPacker, PackingError
from .policy import decide_compression
from .relevance import RelevanceScorer
from .semantic import SemanticProcessor
from .tokenizer import ApproximateTokenCounter, TokenCounter


class ContextCompiler:
    """Компилирует context, не удаляя raw data без persistence confirmation."""

    def __init__(
        self,
        *,
        policy: ContextPolicy = ContextPolicy.ADAPTIVE,
        budget_manager: ContextBudgetManager | None = None,
        token_counter: TokenCounter | None = None,
        classifier: MessageClassifier | None = None,
        pager: MemoryPager | None = None,
        worker_pool: WorkerPool | None = None,
        world_model: BoosterWorldModelAdapter | None = None,
        project_memory: ProjectMemoryAdapter | None = None,
        semantic_enabled: bool = True,
        enrichment_enabled: bool = True,
    ) -> None:
        self.policy = policy
        self.token_counter = token_counter or ApproximateTokenCounter()
        self.budget_manager = budget_manager or ContextBudgetManager()
        self.classifier = classifier or MessageClassifier()
        self.pager = pager or MemoryPager(
            ArtifactStore(Path.cwd() / ".agents" / "booster" / "runtime")
        )
        self.semantic = SemanticProcessor(worker_pool)
        self.world_model = world_model
        self.project_memory = project_memory
        self.semantic_enabled = semantic_enabled
        self.enrichment_enabled = enrichment_enabled
        self.scorer = RelevanceScorer()
        self.packer = ContextPacker(self.token_counter)

    async def compile(
        self,
        request: ChatCompletionRequest,
        session: SessionContext,
        model: ModelProfile,
    ) -> CompiledContext:
        """Выполняет classification -> normalization -> retrieval -> budget -> pack -> integrity."""
        if not isinstance(request, ChatCompletionRequest):
            request = ChatCompletionRequest.model_validate(request)
        if not isinstance(session, SessionContext):
            session = SessionContext.model_validate(session)
        if not isinstance(model, ModelProfile):
            model = ModelProfile.model_validate(model)
        messages = request.messages
        original_tokens = self.token_counter.count_messages(messages)
        try:
            budget = self.budget_manager.calculate(model.context_window, request.max_tokens)
        except ContextBudgetError as exc:
            raise ContextIntegrityError(
                "запрошенный output budget не оставляет input budget"
            ) from exc
        if self.policy == ContextPolicy.OFF:
            if budget.input_hard_limit is not None and original_tokens > budget.input_hard_limit:
                raise ContextIntegrityError("контекст превышает известный hard input budget")
            return CompiledContext(
                messages=list(messages),
                original_tokens=original_tokens,
                compiled_tokens=original_tokens,
                removed_tokens=0,
                compression_ratio=1.0,
                policy=self.policy,
            )

        blocks = self._classify(messages)
        task = self._active_task(messages)
        operations: list[ContextOperation] = []
        artifact_refs: list[str] = []
        warnings: list[str] = []

        for block in blocks:
            before = self.token_counter.count_text(block.content)
            normalized = deterministic_normalize(block.content, block.category)
            if normalized != block.content:
                metadata = await self.pager.persist_before_evict(
                    session.session_id, block, task_id=session.session_id
                )
                block.original_ref = metadata.id
                artifact_refs.append(metadata.id)
                block.content = normalized
                after = self.token_counter.count_text(normalized)
                operations.append(
                    ContextOperation(
                        operation="deterministic_normalize",
                        block_id=block.id,
                        reason="ANSI/dedup/progress/stack/noise normalization",
                        before_tokens=before,
                        after_tokens=after,
                        artifact_ref=metadata.id,
                    )
                )

        input_tokens = sum(self.token_counter.count_text(block.content) + 4 for block in blocks)
        decision = decide_compression(
            self.policy,
            input_tokens,
            budget.soft_target,
            noise_score=self._noise_score(blocks),
            active_errors=sum(
                1 for block in blocks if block.category == ContextCategory.DIAGNOSTIC
            ),
            file_count=len(session.working_set.get("files", [])),
            worker_capacity=self.semantic.pool.max_concurrency if self.semantic.pool else 0,
        )

        for block in blocks:
            block.relevance = self.scorer.score(
                block,
                task,
                active_files=set(session.working_set.get("files", [])),
            )

        if decision.use_semantic and self.semantic_enabled and self.semantic.pool is not None:
            worker_results = await self.semantic.process(blocks, task, model)
            self._apply_worker_results(blocks, worker_results, operations)

        if decision.use_retrieval and self.enrichment_enabled and self.world_model is not None:
            enrichment = await self.world_model.enrich(
                task, session, max_tokens=max(256, budget.soft_target or 2048)
            )
            blocks.extend(enrichment.blocks)
            warnings.extend(enrichment.warnings)
            for block in enrichment.blocks:
                operations.append(
                    ContextOperation(
                        operation="retrieve",
                        block_id=block.id,
                        reason="targeted Booster world model enrichment",
                    )
                )

        if decision.use_retrieval and self.enrichment_enabled and self.project_memory is not None:
            memory_blocks = await self.project_memory.recall(task)
            blocks.extend(memory_blocks)
            for block in memory_blocks:
                operations.append(
                    ContextOperation(
                        operation="retrieve",
                        block_id=block.id,
                        reason="validated project memory candidate; untrusted context",
                    )
                )

        target = (
            budget.soft_target
            if budget.soft_target and input_tokens > budget.soft_target
            else budget.input_hard_limit
        )
        selected, omitted = await self._allocate(
            blocks,
            target,
            budget.input_hard_limit,
            session.session_id,
            artifact_refs,
            operations,
        )
        try:
            packed = self.packer.pack(selected, max_tokens=budget.input_hard_limit)
        except PackingError as exc:
            raise ContextIntegrityError(
                "protected context не помещается в hard input budget"
            ) from exc
        compiled_tokens = self.token_counter.count_messages(packed)
        removed_tokens = max(0, original_tokens - compiled_tokens)
        ratio = compiled_tokens / original_tokens if original_tokens else 1.0
        return CompiledContext(
            messages=packed,
            original_tokens=original_tokens,
            compiled_tokens=compiled_tokens,
            removed_tokens=removed_tokens,
            retrieved_tokens=sum(
                self.token_counter.count_text(block.content)
                for block in blocks
                if block.source != "request"
            ),
            compression_ratio=ratio,
            operations=operations,
            artifact_refs=sorted(set(artifact_refs)),
            policy=self.policy,
            warnings=warnings,
        )

    def _classify(self, messages: Sequence[Message]) -> list[ContextBlock]:
        latest_user = max(
            (index for index, message in enumerate(messages) if message.role.lower() == "user"),
            default=-1,
        )
        latest_tool = max(
            (index for index, message in enumerate(messages) if message.role.lower() == "tool"),
            default=-1,
        )
        blocks: list[ContextBlock] = []
        for index, message in enumerate(messages):
            classification = self.classifier.classify(message)
            priority = classification.priority
            if message.role.lower() == "user" and index != latest_user and priority == Priority.P0:
                priority = Priority.P2
            if message.role.lower() == "user" and index == latest_user and priority == Priority.P1:
                priority = Priority.P0
            if message.role.lower() == "tool" and index != latest_tool and priority == Priority.P1:
                priority = Priority.P2
            extra = dict(message.model_extra or {})
            block = ContextBlock(
                source="request",
                category=classification.category,
                content=message.text,
                priority=priority,
                role=message.role,
                tool_call_id=message.tool_call_id,
                tool_name=classification.tool_name,
                metadata={
                    "message_index": index,
                    "message_extra": extra,
                    "tool_calls": message.tool_calls,
                    "tool_call_ids": [
                        item.get("id")
                        for item in message.tool_calls or []
                        if isinstance(item, dict) and item.get("id")
                    ],
                    "recency": index / max(1, len(messages)),
                },
            )
            blocks.append(block)
        return blocks

    @staticmethod
    def _active_task(messages: Sequence[Message]) -> str:
        for message in reversed(messages):
            if message.role.lower() == "user" and message.text.strip():
                return message.text[:8000]
        return ""

    @staticmethod
    def _noise_score(blocks: Sequence[ContextBlock]) -> float:
        if not blocks:
            return 0.0
        noisy = sum(
            1
            for block in blocks
            if block.category in {ContextCategory.TERMINAL, ContextCategory.BUILD_OUTPUT}
            and len(block.content) > 1000
        )
        return noisy / len(blocks)

    @staticmethod
    def _apply_worker_results(
        blocks: list[ContextBlock], results: list[Any], operations: list[ContextOperation]
    ) -> None:
        # Worker inference не является source of truth; summary применяется только как
        # derived untrusted block и никогда не удаляет исходные blocks сам по себе.
        for result in results:
            if result.status != "success" or not result.summary:
                continue
            summary = f"[derived worker summary; verify against raw artifact]\n{result.summary}"
            blocks.append(
                ContextBlock(
                    source="semantic_worker",
                    category=ContextCategory.UNKNOWN,
                    content=summary,
                    priority=Priority.P2,
                    relevance=0.45,
                    recoverable=True,
                    metadata={"untrusted": True, "worker_channel": result.channel},
                )
            )
            operations.append(
                ContextOperation(
                    operation="semantic_summary",
                    block_id=blocks[-1].id,
                    reason=f"structured worker result for channel {result.channel}",
                )
            )

    async def _allocate(
        self,
        blocks: list[ContextBlock],
        target: int | None,
        hard_limit: int | None,
        session_id: str,
        artifact_refs: list[str],
        operations: list[ContextOperation],
    ) -> tuple[list[ContextBlock], list[ContextBlock]]:
        if target is None:
            return blocks, []
        protected = [block for block in blocks if block.priority <= Priority.P1]
        protected_tokens = sum(
            self.token_counter.count_text(block.content) + 4 for block in protected
        )
        if protected_tokens > target:
            # Soft target не должен вытеснять protected context. В этом случае
            # пробуем полный hard budget и fail-closed только если он тоже мал.
            if hard_limit is not None and protected_tokens <= hard_limit:
                target = hard_limit
            else:
                raise ContextIntegrityError("protected blocks превышают hard context budget")
        candidates = sorted(
            (block for block in blocks if block.priority > Priority.P1),
            key=lambda block: (
                -block.relevance,
                int(block.priority),
                -int(block.metadata.get("message_index", -1)),
            ),
        )
        selected = list(protected)
        selected_ids = {block.id for block in selected}
        used = protected_tokens
        omitted: list[ContextBlock] = []
        for block in candidates:
            cost = self.token_counter.count_text(block.content) + 4
            if used + cost <= target:
                selected.append(block)
                selected_ids.add(block.id)
                used += cost
            else:
                if block.id not in selected_ids:
                    if block.original_ref is None:
                        metadata = await self.pager.persist_before_evict(session_id, block)
                        block.original_ref = metadata.id
                        artifact_refs.append(metadata.id)
                    omitted.append(block)
                    operations.append(
                        ContextOperation(
                            operation="evict",
                            block_id=block.id,
                            reason="lower relevance / budget allocation",
                            before_tokens=cost,
                            after_tokens=0,
                            artifact_ref=block.original_ref,
                        )
                    )
        selected.sort(key=lambda block: int(block.metadata.get("message_index", 0)))
        return selected, omitted
