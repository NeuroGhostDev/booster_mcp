"""Детерминированная классификация message/tool/analyzer blocks."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import ContextCategory, Message, Priority


@dataclass(frozen=True, slots=True)
class Classification:
    category: ContextCategory
    priority: Priority
    tool_name: str | None = None
    reason: str = ""


class MessageClassifier:
    """Сначала использует role/metadata/patterns, не LLM."""

    _diagnostic = re.compile(
        r"(?i)\b(error|warning|traceback|diagnostic|pyright|ruff|rust-analyzer|tsc)\b"
    )
    _terminal = re.compile(r"(?i)(^\s*[$>]\s+|exit code|stdout|stderr|command\s*:|terminal)")
    _test = re.compile(
        r"(?i)(pytest|cargo test|npm test|test_\w+|failed tests?|passed|assertionerror)"
    )
    _build = re.compile(
        r"(?i)(cargo check|cargo build|npm run build|tsc|webpack|compile|build output)"
    )

    def classify(self, message: Message) -> Classification:
        role = message.role.lower()
        tool_name = message.name or None
        text = message.text
        lowered_tool = (tool_name or "").lower()
        if role == "system":
            return Classification(ContextCategory.SYSTEM, Priority.P0, tool_name, "role=system")
        if role == "user":
            if self._diagnostic.search(text) and len(text) > 200:
                return Classification(
                    ContextCategory.DIAGNOSTIC, Priority.P1, tool_name, "user diagnostic payload"
                )
            return Classification(ContextCategory.USER_TASK, Priority.P0, tool_name, "role=user")
        if role == "tool" or lowered_tool in {"terminal", "run_command", "execute", "shell"}:
            category = (
                ContextCategory.TERMINAL
                if self._terminal.search(text) or lowered_tool
                else ContextCategory.TOOL_RESULT
            )
            return Classification(category, Priority.P1, tool_name, "tool result")
        if role == "assistant" and message.tool_calls:
            return Classification(
                ContextCategory.TOOL_CALL, Priority.P1, tool_name, "assistant tool call"
            )
        if role == "assistant":
            if "reasoning_content" in (message.model_extra or {}):
                return Classification(
                    ContextCategory.ASSISTANT_REASONING_RESULT,
                    Priority.P2,
                    tool_name,
                    "provider reasoning",
                )
            return Classification(
                ContextCategory.ASSISTANT_RESPONSE, Priority.P2, tool_name, "role=assistant"
            )
        if self._diagnostic.search(text):
            return Classification(
                ContextCategory.DIAGNOSTIC, Priority.P1, tool_name, "diagnostic pattern"
            )
        if self._test.search(text):
            return Classification(
                ContextCategory.TEST_OUTPUT, Priority.P2, tool_name, "test pattern"
            )
        if self._build.search(text):
            return Classification(
                ContextCategory.BUILD_OUTPUT, Priority.P2, tool_name, "build pattern"
            )
        if text.lstrip().startswith(("diff --git", "+++ ", "--- ")):
            return Classification(ContextCategory.DIFF, Priority.P1, tool_name, "diff pattern")
        if "```" in text or re.search(r"(?m)^\s*(def |class |function |fn |import |from )", text):
            return Classification(
                ContextCategory.SOURCE_CODE, Priority.P2, tool_name, "source pattern"
            )
        return Classification(
            ContextCategory.UNKNOWN, Priority.P3, tool_name, "no deterministic match"
        )


def classify_message(message: Message) -> Classification:
    """Удобная stateless facade для небольших adapters/tests."""
    return MessageClassifier().classify(message)
