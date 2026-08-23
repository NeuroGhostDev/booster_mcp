"""Типизированные lifecycle events без исполнения project content."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .logging import redact_mapping


class EventType(StrEnum):
    REQUEST_RECEIVED = "REQUEST_RECEIVED"
    CONTEXT_COMPILED = "CONTEXT_COMPILED"
    ARTIFACT_STORED = "ARTIFACT_STORED"
    ARTIFACT_RETRIEVED = "ARTIFACT_RETRIEVED"
    DIAGNOSTIC_CHANGED = "DIAGNOSTIC_CHANGED"
    MODEL_REQUEST = "MODEL_REQUEST"
    MODEL_RESPONSE = "MODEL_RESPONSE"
    WORKER_TASK = "WORKER_TASK"
    WORKER_RESULT = "WORKER_RESULT"
    COMPILER_FALLBACK = "COMPILER_FALLBACK"


class TelemetryEvent(BaseModel):
    """Envelope событий для local `/booster/events`."""

    model_config = ConfigDict(extra="allow")

    type: EventType
    session_id: str
    request_id: str
    timestamp: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("session_id", "request_id")
    @classmethod
    def validate_ids(cls, value: str) -> str:
        if not value.strip() or len(value) > 256:
            raise ValueError("некорректный telemetry id")
        return value

    def redacted(self) -> "TelemetryEvent":
        payload = redact_mapping(self.payload)
        return self.model_copy(update={"payload": payload})


def validate_event(value: dict[str, Any]) -> TelemetryEvent:
    """Проверяет envelope и возвращает redacted copy."""
    return TelemetryEvent.model_validate(value).redacted()
