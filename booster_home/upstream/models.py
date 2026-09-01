"""Модели и ошибки OpenAI-compatible upstream."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..models import ModelProfile


class UpstreamError(RuntimeError):
    """Безопасная ошибка upstream без URL и Authorization header."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        details: Any = None,
        transient: bool = False,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.details = details
        self.transient = transient
        super().__init__(message)


class ModelInfo(BaseModel):
    """Нормализованная запись `/v1/models`."""

    model_config = ConfigDict(extra="allow")

    id: str
    object: str = "model"
    owned_by: str = "unknown"
    created: int | None = None

    def profile(self) -> ModelProfile:
        extras = self.model_extra or {}
        context_window = next(
            (
                extras.get(key)
                for key in (
                    "context_window",
                    "context_length",
                    "max_context_length",
                    "max_model_len",
                )
                if isinstance(extras.get(key), int) and extras.get(key) > 0
            ),
            None,
        )
        capabilities = extras.get("capabilities", [])
        return ModelProfile(
            id=self.id,
            context_window=context_window,
            tokenizer=extras.get("tokenizer"),
            supports_tools=bool(extras.get("supports_tools", True)),
            supports_streaming=bool(extras.get("supports_streaming", True)),
            supports_json_schema=bool(extras.get("supports_json_schema", False)),
            supports_responses=bool(extras.get("supports_responses", False)),
            capabilities=(
                set(capabilities) if isinstance(capabilities, list | set | tuple) else set()
            ),
            source="upstream-metadata",
        )


class ModelList(BaseModel):
    """OpenAI-compatible models envelope."""

    model_config = ConfigDict(extra="allow")

    object: str = "list"
    data: list[ModelInfo] = Field(default_factory=list)
