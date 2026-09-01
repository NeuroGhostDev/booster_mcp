from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from booster_web.app import create_app
from booster_web.facade import BoosterFacade
from booster_web.security import RepositoryAllowlist


class FakeIndexer:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.source = self.root / "indexer.py"

    def find_symbols(self, query: str) -> list[dict[str, object]]:
        if query in {"full_index", "RepoIndexer.full_index"}:
            return [{"name": query, "file": str(self.source), "start": 122}]
        return []

    def index_health(self) -> dict[str, object]:
        return {
            "repository": str(self.root),
            "generation_id": "generation-test",
            "ready": True,
        }

    def stats(self) -> dict[str, object]:
        return {"generation_id": "generation-test", "vectors_in_faiss": 1}


def make_client(
    tmp_path: Path,
    *,
    search_lookup=None,
    impact_lookup=None,
    history_lookup=None,
    diagnostics_lookup=None,
) -> TestClient:
    source = tmp_path / "indexer.py"
    source.write_text("\n" * 122 + "def full_index():\n", encoding="utf-8")
    facade = BoosterFacade(
        FakeIndexer(tmp_path),
        RepositoryAllowlist({"demo": tmp_path}),
        search_lookup=search_lookup,
        impact_lookup=impact_lookup,
        history_lookup=history_lookup,
        diagnostics_lookup=diagnostics_lookup,
    )
    return TestClient(create_app(facade=facade))


def test_status_endpoint(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/v1/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "ready"
    assert payload["repo_id"] == "demo"
    assert payload["generation_id"] == "generation-test"
    assert payload["capabilities"] == [
        "focus",
        "search",
        "impact",
        "history",
        "diagnostics",
        "related_tests",
        "snapshots",
        "architecture",
    ]
    assert payload["meta"]["duration_ms"] >= 0


def test_focus_symbol_success(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/symbol/focus",
            json={"repo_id": "demo", "query": "RepoIndexer.full_index"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["result"]["symbol"] == {
        "name": "RepoIndexer.full_index",
        "path": "indexer.py",
        "line": 123,
    }
    assert payload["ui"]["focus"] == {"path": "indexer.py"}
    assert payload["repo"]["id"] == "demo"


def test_symbol_not_found_is_normalized(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/symbol/focus",
            json={"repo_id": "demo", "query": "missing"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "SYMBOL_NOT_FOUND",
        "message": "Symbol not found",
        "retryable": False,
    }
    assert "traceback" not in response.text.lower()


def test_invalid_repo_id_is_not_a_filesystem_lookup(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/symbol/focus",
            json={"repo_id": "not-allowlisted", "query": "full_index"},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "REPO_NOT_FOUND"


def test_invalid_request_is_normalized(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/symbol/focus",
            json={"repo_id": "demo", "query": "", "extra": "rejected"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ARGUMENT"


def test_internal_lookup_error_is_normalized(tmp_path: Path) -> None:
    facade = BoosterFacade(
        FakeIndexer(tmp_path),
        RepositoryAllowlist({"demo": tmp_path}),
        symbol_lookup=lambda _query: (_ for _ in ()).throw(RuntimeError("secret traceback")),
    )
    with TestClient(create_app(facade=facade)) as client:
        response = client.post(
            "/api/v1/symbol/focus",
            json={"repo_id": "demo", "query": "full_index"},
        )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret traceback" not in response.text


def test_search_endpoint_returns_highlights(tmp_path: Path) -> None:
    source = tmp_path / "indexer.py"
    source.write_text("def target():\n", encoding="utf-8")
    with make_client(
        tmp_path,
        search_lookup=lambda _query, _limit: [
            {"file": str(source), "symbol": "target", "retrieval": {"score": 0.91}}
        ],
    ) as client:
        response = client.post(
            "/api/v1/search",
            json={"repo_id": "demo", "query": "target", "limit": 8},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["matches"] == [
        {"path": "indexer.py", "symbol": "target", "score": 0.91}
    ]
    assert payload["ui"] == {
        "highlights": ["indexer.py"],
        "mode": "search",
    }


def test_impact_endpoint_returns_normalized_graph_summary(tmp_path: Path) -> None:
    source = tmp_path / "service.py"
    source.write_text("def service():\n", encoding="utf-8")
    with make_client(
        tmp_path,
        impact_lookup=lambda target, repo, max_depth: {
            "target": target,
            "matches": [{"file": str(source)}],
            "affected_files": [str(source)],
            "direct_callers": ["controller"],
            "direct_callees": ["repository"],
            "suggested_tests": [],
            "risk": {"level": "low", "score": 4},
        },
    ) as client:
        response = client.post(
            "/api/v1/impact",
            json={"repo_id": "demo", "target": "service", "max_depth": 3},
        )

    assert response.status_code == 200
    assert response.json()["result"] == {
        "target": "service",
        "target_file": "service.py",
        "affected_files": ["service.py"],
        "callers": ["controller"],
        "callees": ["repository"],
        "tests": [],
        "connections": [],
        "depth": 3,
        "risk": {"level": "low", "score": 4.0},
    }


def test_phase2_limits_are_normalized_as_invalid_arguments(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        search_response = client.post(
            "/api/v1/search",
            json={"repo_id": "demo", "query": "ok", "limit": 21},
        )
        impact_response = client.post(
            "/api/v1/impact",
            json={"repo_id": "demo", "target": "service", "max_depth": 5},
        )

    assert search_response.status_code == 400
    assert search_response.json()["error"]["code"] == "INVALID_ARGUMENT"
    assert impact_response.status_code == 400
    assert impact_response.json()["error"]["code"] == "INVALID_ARGUMENT"


def test_history_endpoint_returns_compact_history(tmp_path: Path) -> None:
    source = tmp_path / "service.py"
    source.write_text("def service():\n", encoding="utf-8")
    with make_client(
        tmp_path,
        history_lookup=lambda path, symbol, repo, limit: {
            "path": str(source),
            "symbol": symbol,
            "commits": [
                {
                    "hash": "a" * 40,
                    "short_hash": "a" * 12,
                    "author": "Test",
                    "date": "2026-01-01",
                    "message": "Initial service",
                }
            ],
            "blame": [],
            "history_hint": "Nearest change context",
        },
    ) as client:
        response = client.post(
            "/api/v1/history",
            json={"repo_id": "demo", "path": "service.py", "limit": 8},
        )

    assert response.status_code == 200
    assert response.json()["result"]["path"] == "service.py"
    assert response.json()["result"]["commits"][0]["message"] == "Initial service"
    assert response.json()["ui"] == {
        "focus": {"path": "service.py"},
        "highlights": ["service.py"],
        "mode": "history",
    }


def test_diagnostics_endpoint_forces_read_only_runtime_mode(tmp_path: Path) -> None:
    source = tmp_path / "service.py"
    source.write_text("def service():\n", encoding="utf-8")
    seen = {}

    def diagnostics_lookup(paths, repo, include_security, run_external, timeout):
        seen.update(
            paths=paths,
            repo=repo,
            include_security=include_security,
            run_external=run_external,
            timeout=timeout,
        )
        return {
            "paths_checked": paths,
            "summary": {"status": "passed", "total": 0, "by_severity": {}},
            "findings": [],
        }

    with make_client(tmp_path, diagnostics_lookup=diagnostics_lookup) as client:
        response = client.post(
            "/api/v1/diagnostics",
            json={"repo_id": "demo", "paths": ["service.py"]},
        )

    assert response.status_code == 200
    assert seen == {
        "paths": [str(source.resolve())],
        "repo": str(tmp_path.resolve()),
        "include_security": False,
        "run_external": False,
        "timeout": 30,
    }
    assert response.json()["result"]["summary"]["status"] == "passed"


def test_related_tests_endpoint_returns_ranked_paths(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "test_service.py"
    test_file.parent.mkdir()
    test_file.write_text("", encoding="utf-8")
    with make_client(
        tmp_path,
        impact_lookup=lambda *_args: {"suggested_tests": [str(test_file)]},
    ) as client:
        response = client.post(
            "/api/v1/related-tests",
            json={"repo_id": "demo", "target": "service", "limit": 8},
        )

    assert response.status_code == 200
    assert response.json()["result"] == {
        "target": "service",
        "tests": [{"path": "tests/test_service.py", "relation": "name"}],
    }


def test_history_requires_path_or_symbol(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post("/api/v1/history", json={"repo_id": "demo"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ARGUMENT"


def test_architecture_endpoint_returns_repo_map_projection(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text("def service():\n", encoding="utf-8")
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/architecture",
            json={"repo_id": "demo", "focus": "service.py"},
        )

    assert response.status_code == 200
    assert response.json()["result"]["focus"] == "service.py"
    assert response.json()["ui"]["mode"] == "architecture"
    assert "service.py" in response.json()["result"]["map"]


def test_browser_shell_and_modules_are_served_same_origin(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        page = client.get("/")
        store = client.get("/static/workspace-store.js")
        registry = client.get("/static/webmcp-registry.js")

    assert page.status_code == 200
    assert 'type="module"' in page.text
    assert store.status_code == 200
    assert "BoosterWorkspaceStore" in store.text
    assert registry.status_code == 200
    assert "registerTool" in registry.text
