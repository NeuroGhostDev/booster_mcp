"""Решение, когда semantic worker принесёт измеримую пользу."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import ContextPolicy


@dataclass(frozen=True, slots=True)
class CompressionDecision:
    use_deterministic: bool
    use_semantic: bool
    use_retrieval: bool
    reason: str


def decide_compression(
    policy: ContextPolicy,
    input_tokens: int,
    soft_target: int | None,
    *,
    noise_score: float = 0.0,
    active_errors: int = 0,
    file_count: int = 0,
    worker_capacity: int = 1,
) -> CompressionDecision:
    if policy == ContextPolicy.OFF:
        return CompressionDecision(False, False, False, "policy=off")
    if policy == ContextPolicy.SAFE:
        return CompressionDecision(True, False, False, "policy=safe")
    if (
        soft_target is not None
        and input_tokens <= soft_target
        and noise_score < 0.25
        and active_errors == 0
    ):
        return CompressionDecision(True, False, False, "малый low-noise request")
    benefit = input_tokens > (soft_target or 0) or noise_score >= 0.25 or active_errors > 0
    semantic = worker_capacity > 0 and benefit
    # Retrieval остаётся полезным и при временно недоступном worker pool.
    retrieval = benefit and (file_count > 0 or active_errors > 0)
    return CompressionDecision(True, semantic, retrieval, "adaptive benefit threshold reached")
