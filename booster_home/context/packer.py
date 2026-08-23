"""Context packing с protected blocks и tool-call pairing."""

from __future__ import annotations

from collections.abc import Sequence

from ..models import ContextBlock, ContextCategory, Message, Priority
from .tokenizer import ApproximateTokenCounter, TokenCounter


class PackingError(RuntimeError):
    """Невозможно упаковать protected context в hard budget."""


class ContextPacker:
    """Сохраняет logical order и не оставляет tool result без call."""

    def __init__(self, token_counter: TokenCounter | None = None) -> None:
        self.token_counter = token_counter or ApproximateTokenCounter()

    def _message(self, block: ContextBlock) -> Message:
        extra = dict(block.metadata.get("message_extra", {}))
        if block.tool_call_id:
            extra["tool_call_id"] = block.tool_call_id
        if block.metadata.get("tool_calls"):
            extra["tool_calls"] = block.metadata["tool_calls"]
        return Message(
            role=block.role or self._role_for(block.category), content=block.content, **extra
        )

    @staticmethod
    def _role_for(category: ContextCategory) -> str:
        if category == ContextCategory.SYSTEM:
            return "system"
        if category in {
            ContextCategory.USER_TASK,
            ContextCategory.PROJECT_MEMORY,
            ContextCategory.REPO_CONTEXT,
        }:
            return "user"
        if category in {
            ContextCategory.TOOL_RESULT,
            ContextCategory.TERMINAL,
            ContextCategory.DIAGNOSTIC,
        }:
            return "tool"
        return "assistant"

    def pack(
        self,
        blocks: Sequence[ContextBlock],
        max_tokens: int | object | None = None,
    ) -> list[Message]:
        if max_tokens is not None and not isinstance(max_tokens, int):
            max_tokens = getattr(max_tokens, "input_hard_limit", None)
        ordered = sorted(blocks, key=lambda block: int(block.metadata.get("message_index", 0)))
        protected = [block for block in ordered if block.priority <= Priority.P1]
        protected_tokens = sum(
            self.token_counter.count_text(block.content) + 4 for block in protected
        )
        if max_tokens is not None and protected_tokens > max_tokens:
            raise PackingError("protected context превышает input hard limit")
        selected: list[ContextBlock] = list(protected)
        selected_ids = {block.id for block in selected}
        candidates = sorted(
            (block for block in ordered if block.id not in selected_ids),
            key=lambda block: (
                -block.relevance,
                int(block.priority),
                int(block.metadata.get("message_index", 0)),
            ),
        )
        current = protected_tokens
        for block in candidates:
            cost = self.token_counter.count_text(block.content) + 4
            if max_tokens is not None and current + cost > max_tokens:
                continue
            selected.append(block)
            current += cost
        selected.sort(key=lambda block: int(block.metadata.get("message_index", 0)))

        # Если tool result выбран, его matching call тоже обязан остаться.
        call_ids = {
            call_id
            for block in selected
            if block.category == ContextCategory.TOOL_CALL
            for call_id in block.metadata.get("tool_call_ids", [])
        }
        for block in ordered:
            if (
                block.category == ContextCategory.TOOL_RESULT
                and block.tool_call_id
                and block.tool_call_id in call_ids
                and block.id not in {item.id for item in selected}
            ):
                selected.append(block)
        selected_ids = {item.id for item in selected}
        for block in ordered:
            if block.category != ContextCategory.TOOL_RESULT or not block.tool_call_id:
                continue
            if not any(
                item.category == ContextCategory.TOOL_CALL
                and block.tool_call_id in item.metadata.get("tool_call_ids", [])
                for item in selected
            ):
                matching_call = next(
                    (
                        item
                        for item in ordered
                        if item.category == ContextCategory.TOOL_CALL
                        and block.tool_call_id in item.metadata.get("tool_call_ids", [])
                    ),
                    None,
                )
                if matching_call is not None and matching_call.id not in selected_ids:
                    selected.append(matching_call)
                    selected_ids.add(matching_call.id)
        selected.sort(key=lambda block: int(block.metadata.get("message_index", 0)))
        if max_tokens is not None:
            final_tokens = sum(
                self.token_counter.count_text(block.content) + 4 for block in selected
            )
            if final_tokens > max_tokens:
                raise PackingError("tool-call/result pairing превышает input hard limit")
        return [self._message(block) for block in selected]
