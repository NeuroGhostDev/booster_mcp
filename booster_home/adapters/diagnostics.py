"""DiagnosticSource protocol и адаптер существующего CognitiveRuntime."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..context.diagnostic import Diagnostic, normalize_diagnostics


@dataclass(slots=True)
class DiagnosticCollection:
    status: str
    diagnostics: list[Diagnostic] = field(default_factory=list)
    error: str | None = None
    source: str = "unknown"

    def __iter__(self):
        return iter(self.diagnostics)

    def __len__(self) -> int:
        return len(self.diagnostics)


class DiagnosticSource(Protocol):
    async def collect(
        self, repo: Path, files: list[Path] | None = None
    ) -> DiagnosticCollection: ...


class CognitiveRuntimeDiagnosticSource:
    """Переводит legacy dict findings в Unified Diagnostic."""

    def __init__(self, runtime: Any, *, timeout_seconds: int = 120) -> None:
        self.runtime = runtime
        self.timeout_seconds = timeout_seconds

    async def collect(self, repo: Path, files: list[Path] | None = None) -> DiagnosticCollection:
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.runtime.collect_diagnostics,
                    paths=[str(path) for path in files] if files else None,
                    repo=str(repo),
                    timeout_seconds=self.timeout_seconds,
                ),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            return DiagnosticCollection(
                status="timeout", source="cognitive_runtime", error="diagnostic collection timeout"
            )
        except Exception as exc:
            return DiagnosticCollection(
                status="error", source="cognitive_runtime", error=type(exc).__name__
            )
        if not isinstance(result, dict):
            return DiagnosticCollection(
                status="error", source="cognitive_runtime", error="invalid adapter result"
            )
        diagnostics = normalize_diagnostics(result.get("findings", []), source="cognitive_runtime")
        return DiagnosticCollection(
            status="ok", diagnostics=diagnostics, source="cognitive_runtime"
        )
