"""Типизированные модели research coprocessor."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResearchModel(BaseModel):
    """Модель, сохраняющая дополнительные поля научных артефактов."""

    model_config = ConfigDict(extra="allow")


class ResearchMode(StrEnum):
    """Режим формирования research context."""

    CODING = "coding"
    DEBUG = "debug"
    RESEARCH = "research"
    REVIEW = "review"
    BENCHMARK = "benchmark"


class HypothesisStatus(StrEnum):
    """Допустимый жизненный цикл гипотезы."""

    PROPOSED = "proposed"
    TESTING = "testing"
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class WorkerRole(StrEnum):
    """Ограниченные роли локального worker-а."""

    LOG_ANALYST = "log_analyst"
    CODE_SEARCH = "code_search"
    TEST_WRITER = "test_writer"
    BENCHMARK_READER = "benchmark_reader"
    DIFF_REVIEWER = "diff_reviewer"
    ARTIFACT_INDEXER = "artifact_indexer"
    SUMMARIZER = "summarizer"


class CheckpointRecord(ResearchModel):
    """Метаданные checkpoint без чтения бинарного тела."""

    path: str
    filename: str
    size_bytes: int = 0
    size: int | None = None
    step: int | None = None
    base_checkpoint: str | None = None
    trainable_groups: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    parent_experiment: str | None = None
    experiment: str | None = None
    status: str | None = None
    keep: bool | None = None
    branch: str | None = None
    metadata_source: str | None = None


class HypothesisRecord(ResearchModel):
    """Зарегистрированная проверяемая гипотеза."""

    id: str
    hypothesis: str
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    evidence_for: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)
    confounds: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    control_arms: list[str] = Field(default_factory=list)
    independent_variable: str | None = None
    dependent_metrics: list[str] = Field(default_factory=list)
    pass_criteria: list[str] = Field(default_factory=list)
    fail_criteria: list[str] = Field(default_factory=list)
    required_artifacts: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence должен находиться в диапазоне 0..1")
        return value


class ResearchBlock(ResearchModel):
    """Один provenance-aware блок context pack."""

    id: str
    layer: str
    source: str
    content: str
    token_count: int = 0
    priority: int = 3
    untrusted: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
