"""Общие fake providers для Home tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from typing import Any

import pytest

from booster_home.upstream.models import ModelInfo, ModelList


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.stream_closed = False

    async def models(self) -> ModelList:
        return ModelList(
            data=[ModelInfo(id="fake-model", context_length=512, supports_responses=True)]
        )

    async def chat_completions(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append(dict(payload))
        return {
            "id": "chatcmpl_fake",
            "object": "chat.completion",
            "model": payload.get("model"),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "ok",
                        "reasoning_content": "reason",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
            "provider_extra": {"kept": True},
        }

    async def chat_completions_stream(self, payload: Mapping[str, Any]) -> AsyncIterator[bytes]:
        self.calls.append(dict(payload))

        async def stream() -> AsyncIterator[bytes]:
            try:
                yield b'data: {"delta":"one"}\n\n'
                await asyncio.sleep(0)
                yield b"data: [DONE]\n\n"
            finally:
                self.stream_closed = True

        return stream()

    async def responses(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append(dict(payload))
        return {
            "id": "resp_fake",
            "object": "response",
            "output": [{"type": "message", "text": "ok"}],
            "provider_extra": "kept",
        }

    async def responses_stream(self, payload: Mapping[str, Any]) -> AsyncIterator[bytes]:
        return self.chat_completions_stream(payload)

    async def close(self) -> None:
        return None


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()
