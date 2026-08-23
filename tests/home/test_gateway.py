from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from booster_home.app import create_app
from booster_home.config import (
    ContextSettings,
    HomeConfig,
    HomeSettings,
    MemorySettings,
    UpstreamSettings,
    WorkerSettings,
)
from booster_home.runtime import HomeDependencies
from booster_home.upstream.models import UpstreamError


def _config(tmp_path) -> HomeConfig:
    return HomeConfig(
        home=HomeSettings(listen="127.0.0.1", port=7797),
        upstream=UpstreamSettings(
            base_url="http://upstream.invalid/v1", model="fake-model", api_key="test-secret"
        ),
        context=ContextSettings(context_window=512, reserve_output=64, safety_margin=16),
        workers=WorkerSettings(max_concurrency=1, timeout_seconds=1),
        memory=MemorySettings(root_dir=tmp_path),
        project=None,
    )


def test_gateway_preserves_unknown_chat_fields_and_redacts_status(tmp_path, fake_provider) -> None:
    app = create_app(_config(tmp_path), HomeDependencies(provider=fake_provider))
    with TestClient(app) as client:
        status = client.get("/booster/status")
        assert status.status_code == 200
        assert "test-secret" not in status.text
        response = client.post(
            "/v1/chat/completions",
            headers={"X-Booster-Session": "session-a"},
            json={
                "model": "fake-model",
                "messages": [{"role": "user", "content": "hello"}],
                "min_p": 0.2,
                "reasoning_effort": "low",
            },
        )
        assert response.status_code == 200
        assert response.json()["provider_extra"]["kept"] is True
        assert fake_provider.calls[-1]["min_p"] == 0.2
        assert fake_provider.calls[-1]["reasoning_effort"] == "low"


def test_gateway_requires_auth_for_non_loopback_bind(tmp_path, fake_provider) -> None:
    token = "t" * 32
    config = HomeConfig(
        home=HomeSettings(listen="0.0.0.0", port=7798, auth_token=token),
        upstream=UpstreamSettings(base_url="http://upstream.invalid/v1", model="fake-model"),
        context=ContextSettings(context_window=512, reserve_output=64, safety_margin=16),
        workers=WorkerSettings(max_concurrency=1, timeout_seconds=1),
        memory=MemorySettings(root_dir=tmp_path),
    )
    with TestClient(create_app(config, HomeDependencies(provider=fake_provider))) as client:
        denied = client.get("/health")
        accepted = client.get("/health", headers={"Authorization": f"Bearer {token}"})

    assert denied.status_code == 401
    assert accepted.status_code == 200


def test_gateway_stream_and_responses(tmp_path, fake_provider) -> None:
    app = create_app(_config(tmp_path), HomeDependencies(provider=fake_provider))
    with TestClient(app) as client:
        stream = client.post(
            "/v1/chat/completions",
            json={
                "model": "fake-model",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
        )
        assert stream.status_code == 200
        assert "data:" in stream.text
        responses = client.post(
            "/v1/responses",
            json={"model": "fake-model", "input": "hello", "unknown_provider_field": 42},
        )
        assert responses.status_code == 200
        assert responses.json()["provider_extra"] == "kept"
        assert fake_provider.calls[-1]["unknown_provider_field"] == 42


def test_responses_chat_fallback_uses_compiled_messages(tmp_path, fake_provider) -> None:
    config = HomeConfig(
        upstream=UpstreamSettings(model="fake-model"),
        context=ContextSettings(context_window=128, reserve_output=16, safety_margin=8),
        workers=WorkerSettings(max_concurrency=1),
        memory=MemorySettings(root_dir=tmp_path),
    )

    async def missing_responses(payload):
        raise UpstreamError("Responses endpoint unavailable", status_code=404)

    fake_provider.responses = missing_responses
    original_input = [
        {"role": "user", "content": f"historical message {index} " + "noise " * 40}
        for index in range(12)
    ]
    with TestClient(create_app(config, HomeDependencies(provider=fake_provider))) as client:
        result = client.post(
            "/v1/responses",
            json={"model": "fake-model", "input": original_input, "max_output_tokens": 16},
        )

    assert result.status_code == 200
    assert len(fake_provider.calls[-1]["messages"]) < len(original_input)


def test_models_endpoint_has_bounded_discovery_fallback(tmp_path, fake_provider) -> None:
    config = _config(tmp_path)
    config.upstream.read_timeout = 0.01

    async def slow_models():
        await asyncio.sleep(1)
        return await fake_provider.models()

    fake_provider.models = slow_models
    with TestClient(create_app(config, HomeDependencies(provider=fake_provider))) as client:
        response = client.get("/v1/models")

    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "fake-model"


def test_chat_profile_discovery_has_bounded_fallback(tmp_path, fake_provider) -> None:
    config = _config(tmp_path)
    config.upstream.read_timeout = 0.01

    async def slow_models():
        await asyncio.sleep(1)
        return await fake_provider.models()

    fake_provider.models = slow_models
    with TestClient(create_app(config, HomeDependencies(provider=fake_provider))) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "fake-model",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

    assert response.status_code == 200
