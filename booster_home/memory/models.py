"""Модели session, timeline, facts и working set."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class MemoryModel(BaseModel):
    model_config = ConfigDict(extra="allow")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Session(MemoryModel):
    session_id: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class Episode(MemoryModel):
    episode_id: str = Field(default_factory=lambda: f"episode_{uuid4().hex}")
    session_id: str
    task: str = ""
    content: str = ""
    artifact_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class Fact(MemoryModel):
    fact_id: str = Field(default_factory=lambda: f"fact_{uuid4().hex}")
    session_id: str
    statement: str
    source: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    validated: bool = False
    superseded: bool = False
    rejected: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class Decision(MemoryModel):
    decision_id: str = Field(default_factory=lambda: f"decision_{uuid4().hex}")
    session_id: str
    statement: str
    status: Literal["proposed", "validated", "rejected", "superseded"] = "proposed"
    source: str
    evidence: list[str] = Field(default_factory=list)
    superseded: bool = False
    rejected: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class WorkingSet(MemoryModel):
    session_id: str
    active_task: str = ""
    files: set[str] = Field(default_factory=set)
    symbols: set[str] = Field(default_factory=set)
    diagnostics: set[str] = Field(default_factory=set)
    decisions: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)


class TimelineEvent(MemoryModel):
    seq: int
    type: str
    timestamp: datetime = Field(default_factory=utc_now)
    request_id: str | None = None
    session_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
