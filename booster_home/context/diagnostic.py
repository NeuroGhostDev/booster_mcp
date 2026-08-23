"""Unified Diagnostic и lifecycle между запросами."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Diagnostic(BaseModel):
    """Нормализованная compiler/LSP/security finding."""

    model_config = ConfigDict(extra="allow")

    source: str
    severity: str = "error"
    code: str | None = None
    file: str | None = None
    line: int | None = None
    column: int | None = None
    message: str
    task_relevance: float = 0.0
    active: bool = True
    fingerprint: str = ""
    related: list[str] = Field(default_factory=list)
    artifact_ref: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if not self.fingerprint:
            # Message намеренно не входит в fingerprint: изменение текста на той
            # же позиции должно быть lifecycle=changed, а не appeared+resolved.
            normalized = "|".join(
                str(item or "").strip().lower()
                for item in (
                    self.source,
                    self.code,
                    self.file,
                    self.line,
                    self.column,
                )
            )
            self.fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def _from_item(item: dict[str, Any], source: str = "unknown") -> Diagnostic | None:
    message = item.get("message") or item.get("msg") or item.get("reason")
    if not isinstance(message, str) or not message.strip():
        return None
    location = item.get("location") if isinstance(item.get("location"), dict) else {}
    return Diagnostic(
        source=str(item.get("source") or source),
        severity=str(item.get("severity") or item.get("level") or "error").lower(),
        code=str(item.get("code")) if item.get("code") is not None else None,
        file=item.get("file") or item.get("filename") or item.get("path") or location.get("path"),
        line=item.get("line") or location.get("line"),
        column=item.get("column") or location.get("column"),
        message=message,
        related=[str(value) for value in item.get("related", []) if value is not None],
    )


def normalize_diagnostics(value: Any, source: str = "unknown") -> list[Diagnostic]:
    """Нормализует Ruff/LSP/cargo-like list/object в unified model."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if isinstance(value, dict):
        if isinstance(value.get("diagnostics"), list):
            value = value["diagnostics"]
        elif isinstance(value.get("data"), list):
            value = value["data"]
        else:
            value = [value]
    if not isinstance(value, list):
        return []
    result: list[Diagnostic] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        diagnostic = _from_item(item, source)
        if diagnostic and diagnostic.fingerprint not in seen:
            result.append(diagnostic)
            seen.add(diagnostic.fingerprint)
    return result


@dataclass(slots=True)
class DiagnosticLifecycle:
    """Отслеживает appeared/repeated/changed/resolved/reappeared."""

    previous: dict[str, Diagnostic] | None = None

    def update(self, diagnostics: list[Diagnostic]) -> dict[str, Any]:
        current = {item.fingerprint: item for item in diagnostics if item.active}
        previous = self.previous or {}
        appeared = sorted(set(current) - set(previous))
        resolved = sorted(set(previous) - set(current))
        repeated = sorted(set(current) & set(previous))
        changed: list[str] = []
        for fingerprint in repeated:
            if current[fingerprint].message != previous[fingerprint].message:
                changed.append(fingerprint)
        reappeared = [item for item in appeared if item in (self._resolved_before or set())]
        self._resolved_before = set(resolved)
        self.previous = current
        return {
            "appeared": appeared,
            "repeated": repeated,
            "changed": sorted(changed),
            "resolved": resolved,
            "reappeared": sorted(reappeared),
            "active_count": len(current),
            "resolved_count": len(resolved),
        }

    _resolved_before: set[str] = field(default_factory=set, init=False)
