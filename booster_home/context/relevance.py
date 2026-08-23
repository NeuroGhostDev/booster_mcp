"""Explainable deterministic relevance scoring."""

from __future__ import annotations

import re

from ..models import ContextBlock, ContextCategory


class RelevanceScorer:
    """Считает task/recency/file/error/rule признаки без ML зависимости."""

    def score(
        self, block: ContextBlock, task: str, *, active_files: set[str] | None = None
    ) -> float:
        task_tokens = set(re.findall(r"[A-Za-zА-Яа-я0-9_]+", task.lower()))
        text_tokens = set(re.findall(r"[A-Za-zА-Яа-я0-9_]+", block.content.lower()))
        similarity = len(task_tokens & text_tokens) / max(1, len(task_tokens))
        recency = float(block.metadata.get("recency", 0.0))
        active_bonus = (
            0.25 if active_files and any(file in block.content for file in active_files) else 0.0
        )
        error_bonus = (
            0.3
            if block.category == ContextCategory.DIAGNOSTIC and block.metadata.get("active", True)
            else 0.0
        )
        rule_bonus = 0.3 if block.category == ContextCategory.PROJECT_MEMORY else 0.0
        duplicate_penalty = 0.3 if block.metadata.get("duplicate") else 0.0
        verbosity_penalty = min(0.25, len(block.content) / 100_000)
        priority_bonus = (4 - int(block.priority)) * 0.05
        return max(
            0.0,
            min(
                1.0,
                similarity
                + recency
                + active_bonus
                + error_bonus
                + rule_bonus
                + priority_bonus
                - duplicate_penalty
                - verbosity_penalty,
            ),
        )
