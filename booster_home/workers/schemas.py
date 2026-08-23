"""Pydantic schemas для observed/inferred/uncertain worker outputs."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkerPayload(BaseModel):
    """Структурированный результат без права подменять source of truth."""

    model_config = ConfigDict(extra="allow")

    observed: list[str] = Field(default_factory=list)
    inferred: list[str] = Field(default_factory=list)
    uncertain: list[str] = Field(default_factory=list)
    summary: str | None = None
    critical: list[str] = Field(default_factory=list)
    new: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)
    duplicates: list[str] = Field(default_factory=list)
    suspected_root_causes: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


def _extract_json(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(
            r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.IGNORECASE | re.DOTALL
        )
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def parse_worker_payload(value: Any) -> WorkerPayload:
    """Парсит JSON/JSON string и отклоняет malformed output."""
    parsed = _extract_json(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("worker output должен быть JSON object")
    return WorkerPayload.model_validate(parsed)
