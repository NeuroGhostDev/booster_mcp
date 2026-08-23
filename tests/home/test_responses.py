from __future__ import annotations

from fastapi.testclient import TestClient

from booster_home.app import create_app
from booster_home.config import (
    ContextSettings,
    HomeConfig,
    MemorySettings,
    UpstreamSettings,
    WorkerSettings,
)
from booster_home.runtime import HomeDependencies


def test_responses_rejects_unsupported_input(tmp_path, fake_provider) -> None:
    config = HomeConfig(
        upstream=UpstreamSettings(model="fake-model"),
        context=ContextSettings(context_window=512, reserve_output=64, safety_margin=16),
        workers=WorkerSettings(max_concurrency=1),
        memory=MemorySettings(root_dir=tmp_path),
    )
    with TestClient(create_app(config, HomeDependencies(provider=fake_provider))) as client:
        result = client.post(
            "/v1/responses", json={"model": "fake-model", "input": {"type": "computer_use"}}
        )
    assert result.status_code == 501
    assert result.json()["error"]["code"] == "unsupported_responses_input"


def test_responses_rejects_unsupported_content_part(tmp_path, fake_provider) -> None:
    config = HomeConfig(
        upstream=UpstreamSettings(model="fake-model"),
        context=ContextSettings(context_window=512, reserve_output=64, safety_margin=16),
        workers=WorkerSettings(max_concurrency=1),
        memory=MemorySettings(root_dir=tmp_path),
    )
    with TestClient(create_app(config, HomeDependencies(provider=fake_provider))) as client:
        result = client.post(
            "/v1/responses",
            json={
                "model": "fake-model",
                "input": [
                    {
                        "role": "user",
                        "content": [{"type": "input_image", "image_url": "https://example.test/x"}],
                    }
                ],
            },
        )

    assert result.status_code == 501
    assert result.json()["error"]["code"] == "unsupported_responses_input"
