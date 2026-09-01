from __future__ import annotations

from pathlib import Path

import pytest

from booster_home.config import HomeConfig, load_home_config


def test_config_precedence_and_redaction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    (user_dir / "home.toml").write_text(
        '[upstream]\nmodel = "user-model"\napi_key = "user-secret"\n', encoding="utf-8"
    )
    monkeypatch.setenv("BOOSTER_HOME_CONFIG_DIR", str(user_dir))
    project = tmp_path / "project"
    (project / ".agents" / "booster").mkdir(parents=True)
    (project / ".agents" / "booster" / "home.toml").write_text(
        "[home]\nport = 7788\n", encoding="utf-8"
    )
    explicit = tmp_path / "explicit.toml"
    explicit.write_text(
        '[upstream]\nmodel = "explicit-model"\napi_key = "explicit-secret"\n', encoding="utf-8"
    )
    config = load_home_config(project, explicit, {"port": 7799})
    assert config.upstream.model == "explicit-model"
    assert config.home.port == 7799
    redacted = config.redacted()
    assert redacted["upstream"]["api_key"] == "***configured***"
    assert "explicit-secret" not in str(redacted)


def test_invalid_context_budget_is_rejected() -> None:
    with pytest.raises(ValueError):
        HomeConfig(context={"context_window": 4096, "reserve_output": 4096, "safety_margin": 1})


def test_redacted_config_removes_endpoint_query_secret() -> None:
    config = HomeConfig(upstream={"base_url": "http://example.test/v1?api_key=query-secret"})

    assert config.redacted()["upstream"]["base_url"] == "http://example.test/v1"


def test_non_loopback_home_requires_auth_token() -> None:
    with pytest.raises(ValueError, match="non-loopback"):
        HomeConfig(home={"listen": "0.0.0.0"})

    config = HomeConfig(
        home={"listen": "0.0.0.0", "auth_token": "t" * 32},
    )
    redacted = config.redacted()
    assert redacted["auth_required"] is True
    assert redacted["home"]["auth_token"] == "***configured***"
    assert "t" * 32 not in str(redacted)
