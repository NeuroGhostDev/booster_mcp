"""Общие типизированные модели Booster Home.

OpenAI и локальные провайдеры часто добавляют собственные поля. Поэтому
сетевые envelope-модели разрешают extra-поля и при сериализации не теряют их.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import IntEnum, StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HomeModel(BaseModel):
    """Базовая модель с прозрачным сохранением неизвестных полей."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ContextPolicy(StrEnum):
    """Политика обработки контекста."""

    OFF = "off"
    SAFE = "safe"
    ADAPTIVE = "adaptive"
    AGGRESSIVE = "aggressive"


class ContextCategory(StrEnum):
    """Детерминированные категории входных блоков."""

    SYSTEM = "system"
    USER_TASK = "user_task"
    ASSISTANT_REASONING_RESULT = "assistant_reasoning_result"
    ASSISTANT_RESPONSE = "assistant_response"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TERMINAL = "terminal"
    DIAGNOSTIC = "diagnostic"
    SOURCE_CODE = "source_code"
    DIFF = "diff"
    REPO_CONTEXT = "repo_context"
    PROJECT_MEMORY = "project_memory"
    BUILD_OUTPUT = "build_output"
    TEST_OUTPUT = "test_output"
    GIT_OUTPUT = "git_output"
    UNKNOWN = "unknown"


class Priority(IntEnum):
    """Приоритет блока: меньшее число означает большую защищённость."""

    P0 = 0
    P1 = 1
    P2 = 2
    P3 = 3
    P4 = 4


class Message(HomeModel):
    """Сообщение OpenAI-compatible API."""

    role: str
    content: Any = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None

    @property
    def text(self) -> str:
        """Возвращает content в форме, пригодной для deterministic pipeline."""
        if self.content is None or self.content == "":
            reasoning = (self.model_extra or {}).get("reasoning_content")
            if isinstance(reasoning, str):
                return reasoning
            return ""
        if isinstance(self.content, str):
            return self.content
        try:
            return json.dumps(self.content, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            return str(self.content)


class ChatCompletionRequest(HomeModel):
    """Входной envelope для `/v1/chat/completions`."""

    model: str
    messages: list[Message] = Field(default_factory=list)
    stream: bool = False
    max_tokens: int | None = None

    @field_validator("max_tokens")
    @classmethod
    def validate_max_tokens(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("max_tokens должен быть положительным")
        return value

    def upstream_payload(self, messages: list[Message] | None = None) -> dict[str, Any]:
        """Сериализует request, заменяя только управляемые compiler-поля."""
        payload = self.model_dump(exclude_none=True)
        if messages is not None:
            payload["messages"] = [message.model_dump(exclude_none=True) for message in messages]
        return payload


class ResponsesRequest(HomeModel):
    """Минимальный envelope Responses API с сохранением provider-полей."""

    model: str
    input: Any = None
    stream: bool = False
    max_output_tokens: int | None = None

    @field_validator("max_output_tokens")
    @classmethod
    def validate_max_output_tokens(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("max_output_tokens должен быть положительным")
        return value

    def upstream_payload(self, input_value: Any = None) -> dict[str, Any]:
        """Возвращает payload без удаления неизвестных полей."""
        payload = self.model_dump(exclude_none=True)
        if input_value is not None:
            payload["input"] = input_value
        return payload


class ModelProfile(HomeModel):
    """Известные возможности конкретной inference-модели."""

    id: str
    context_window: int | None = None
    tokenizer: str | None = None
    supports_tools: bool = True
    supports_streaming: bool = True
    supports_json_schema: bool = False
    supports_responses: bool = False
    capabilities: set[str] = Field(default_factory=set)
    source: str = "safe-fallback"
    warning: str | None = None

    @field_validator("context_window")
    @classmethod
    def validate_context_window(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("context_window должен быть положительным")
        return value


class ContextBlock(HomeModel):
    """Внутренний блок с provenance и возможностью восстановления."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    source: str = "request"
    category: ContextCategory = ContextCategory.UNKNOWN
    content: str = ""
    original_ref: str | None = None
    relevance: float = 0.0
    priority: Priority = Priority.P3
    token_count: int = 0
    recoverable: bool = True
    role: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextOperation(HomeModel):
    """Объяснимое изменение контекста."""

    operation: str
    block_id: str
    reason: str
    before_tokens: int = 0
    after_tokens: int = 0
    artifact_ref: str | None = None


class CompiledContext(HomeModel):
    """Результат полной compiler pipeline."""

    messages: list[Message] = Field(default_factory=list)
    original_tokens: int = 0
    compiled_tokens: int = 0
    removed_tokens: int = 0
    retrieved_tokens: int = 0
    compression_ratio: float = 1.0
    operations: list[ContextOperation] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    policy: ContextPolicy = ContextPolicy.ADAPTIVE
    fallback: bool = False
    integrity_checked: bool = True
    warnings: list[str] = Field(default_factory=list)


class SessionContext(HomeModel):
    """Снимок session state для одного запроса."""

    session_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    working_set: dict[str, Any] = Field(default_factory=dict)
    recent_events: list[dict[str, Any]] = Field(default_factory=list)


class RequestContext(HomeModel):
    """Корреляционные идентификаторы без пользовательских секретов."""

    request_id: str = Field(default_factory=lambda: f"req_{uuid4().hex}")
    session_id: str
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkerJob(HomeModel):
    """Одна ограниченная semantic worker задача."""

    id: str = Field(default_factory=lambda: f"job_{uuid4().hex}")
    channel: str
    content: str
    task: str = "compress"
    model: str | None = None
    prompt_version: str = "home-worker-v1"
    schema_version: str = "worker-v1"
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerResult(HomeModel):
    """Проверенный или детерминированный результат worker."""

    job_id: str
    channel: str
    status: Literal["success", "timeout", "error", "invalid", "deterministic"]
    observed: list[str] = Field(default_factory=list)
    inferred: list[str] = Field(default_factory=list)
    uncertain: list[str] = Field(default_factory=list)
    summary: str | None = None
    reason: str | None = None
    raw_fields: dict[str, Any] = Field(default_factory=dict)
