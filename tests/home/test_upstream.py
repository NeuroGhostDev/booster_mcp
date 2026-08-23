from __future__ import annotations

import json

import httpx
import pytest

from booster_home.config import UpstreamSettings
from booster_home.upstream.provider import OpenAICompatibleProvider, UpstreamError


@pytest.mark.asyncio
async def test_provider_preserves_path_unknown_fields_and_auth() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/v1/models":
            return httpx.Response(
                200, json={"object": "list", "data": [{"id": "model", "context_length": 1234}]}
            )
        return httpx.Response(200, json={"id": "ok", "choices": [], "provider_extra": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        UpstreamSettings(base_url="http://example.test/v1/", api_key="secret"), client
    )
    await provider.models()
    response = await provider.chat_completions(
        {"model": "model", "messages": [], "reasoning_effort": "low", "min_p": 0.2}
    )
    assert response["provider_extra"] is True
    assert seen[0].url.path == "/v1/models"
    assert seen[0].headers["authorization"] == "Bearer secret"
    assert json.loads(seen[1].content)["min_p"] == 0.2
    await client.aclose()


@pytest.mark.asyncio
async def test_provider_does_not_retry_client_errors() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        UpstreamSettings(base_url="http://example.test/v1", max_retries=5), client
    )
    with pytest.raises(UpstreamError) as error:
        await provider.chat_completions({"model": "m", "messages": []})
    assert error.value.status_code == 400
    assert calls == 1
    await client.aclose()
