from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from booster_web.app import create_app
from booster_web.facade import BoosterFacade
from booster_web.security import (
    RateLimitExceeded,
    RepositoryAllowlist,
    WebRequestGuard,
    WebSecuritySettings,
)


def test_allowlist_resolves_only_known_logical_ids(tmp_path: Path) -> None:
    allowlist = RepositoryAllowlist({"demo": tmp_path})

    assert allowlist.resolve_repo("demo") == tmp_path.resolve()
    with pytest.raises(KeyError):
        allowlist.resolve_repo("other")


def test_relative_path_cannot_escape_repository_root(tmp_path: Path) -> None:
    allowlist = RepositoryAllowlist({"demo": tmp_path})

    with pytest.raises(ValueError, match="escapes"):
        allowlist.resolve_relative_path("demo", "../outside.py")


def test_absolute_relative_path_is_rejected(tmp_path: Path) -> None:
    allowlist = RepositoryAllowlist({"demo": tmp_path})

    with pytest.raises(ValueError, match="relative"):
        allowlist.resolve_relative_path("demo", str((tmp_path / "file.py").resolve()))


def test_unsafe_repo_id_is_rejected_before_mapping(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        RepositoryAllowlist({"../escape": tmp_path})


class Indexer:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def find_symbols(self, _query: str) -> list[dict[str, object]]:
        return []

    def index_health(self) -> dict[str, object]:
        return {"repository": str(self.root), "ready": True}

    def stats(self) -> dict[str, object]:
        return {"generation_id": "generation", "vectors_in_faiss": 1}


def test_security_settings_fail_closed_above_public_limits() -> None:
    with pytest.raises(ValueError):
        WebSecuritySettings(max_concurrent=5)
    with pytest.raises(ValueError):
        WebSecuritySettings(timeout_seconds=11)


def test_rate_limit_is_normalized_by_the_web_api(tmp_path: Path) -> None:
    facade = BoosterFacade(Indexer(tmp_path), RepositoryAllowlist({"demo": tmp_path}))
    app = create_app(
        facade=facade,
        security=WebSecuritySettings(rate_limit_requests=1, rate_limit_window_seconds=60),
    )
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        first = client.get("/api/v1/status")
        second = client.get("/api/v1/status")

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"] == {
        "code": "RATE_LIMITED",
        "message": "Request rate limit exceeded",
        "retryable": True,
    }


def test_operation_timeout_is_normalized_without_releasing_worker_slot_early(
    tmp_path: Path,
) -> None:
    def slow_lookup(_query: str):
        time.sleep(0.08)
        return []

    facade = BoosterFacade(
        Indexer(tmp_path),
        RepositoryAllowlist({"demo": tmp_path}),
        symbol_lookup=slow_lookup,
    )
    app = create_app(
        facade=facade,
        security=WebSecuritySettings(timeout_seconds=0.01),
    )
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/symbol/focus",
            json={"repo_id": "demo", "query": "slow"},
        )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "TIMEOUT"


def test_concurrency_limit_rejects_when_all_slots_are_busy() -> None:
    async def run() -> None:
        guard = WebRequestGuard(
            WebSecuritySettings(
                max_concurrent=1,
                timeout_seconds=1,
                rate_limit_requests=10,
            )
        )

        async def slow() -> str:
            await guard.run("client", time.sleep, 0.15)
            return "done"

        first = asyncio.create_task(slow())
        await asyncio.sleep(0.01)
        with pytest.raises(RateLimitExceeded):
            await guard.run("client", lambda: "second")
        assert await first == "done"
        assert await guard.run("client", lambda: "third") == "third"

    asyncio.run(run())
