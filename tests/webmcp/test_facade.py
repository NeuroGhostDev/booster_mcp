from __future__ import annotations

from pathlib import Path

import pytest

from booster_web.cache import ReadOnlyCache
from booster_web.facade import BoosterFacade, FacadeError
from booster_web.models import (
    DiagnosticsRequest,
    HistoryRequest,
    ImpactRequest,
    RelatedTestsRequest,
    SearchRequest,
    SymbolFocusRequest,
)
from booster_web.security import RepositoryAllowlist


class FakeIndexer:
    def __init__(
        self, root: Path, matches: dict[str, list[dict[str, object]]] | None = None
    ) -> None:
        self.root = root.resolve()
        self.matches = matches or {}
        self.queries: list[str] = []

    def find_symbols(self, query: str) -> list[dict[str, object]]:
        self.queries.append(query)
        return self.matches.get(query, [])

    def index_health(self) -> dict[str, object]:
        return {
            "repository": str(self.root),
            "generation_id": "generation-test",
            "ready": True,
        }

    def stats(self) -> dict[str, object]:
        return {"generation_id": "generation-test", "vectors_in_faiss": 1}


def make_facade(
    root: Path, matches: dict[str, list[dict[str, object]]] | None = None
) -> tuple[BoosterFacade, FakeIndexer]:
    indexer = FakeIndexer(root, matches)
    allowlist = RepositoryAllowlist({"demo": root})
    return BoosterFacade(indexer, allowlist), indexer


def test_focus_symbol_normalizes_existing_indexer_location(tmp_path: Path) -> None:
    source = tmp_path / "indexer.py"
    source.write_text("\n" * 122 + "def full_index():\n", encoding="utf-8")
    facade, indexer = make_facade(
        tmp_path,
        {
            "RepoIndexer.full_index": [
                {"name": "RepoIndexer.full_index", "file": str(source), "start": 122}
            ]
        },
    )

    result = facade.focus_symbol(SymbolFocusRequest(repo_id="demo", query="RepoIndexer.full_index"))

    assert result.result.symbol.model_dump() == {
        "name": "RepoIndexer.full_index",
        "path": "indexer.py",
        "line": 123,
    }
    assert result.ui.focus is not None
    assert result.ui.focus.path == "indexer.py"
    assert indexer.queries == ["RepoIndexer.full_index"]


def test_focus_symbol_uses_leaf_fallback_for_existing_unqualified_indexer_symbols(
    tmp_path: Path,
) -> None:
    source = tmp_path / "indexer.py"
    source.write_text("def full_index():\n", encoding="utf-8")
    facade, indexer = make_facade(
        tmp_path,
        {"full_index": [{"name": "full_index", "file": str(source), "start": 0}]},
    )

    result = facade.focus_symbol(SymbolFocusRequest(repo_id="demo", query="RepoIndexer.full_index"))

    assert result.result.symbol.name == "full_index"
    assert indexer.queries == ["RepoIndexer.full_index", "full_index"]


def test_focus_symbol_normalizes_not_found(tmp_path: Path) -> None:
    facade, _ = make_facade(tmp_path)

    with pytest.raises(FacadeError) as raised:
        facade.focus_symbol(SymbolFocusRequest(repo_id="demo", query="missing"))

    assert raised.value.code == "SYMBOL_NOT_FOUND"
    assert raised.value.message == "Symbol not found"


def test_focus_symbol_rejects_match_outside_allowlisted_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.py"
    outside.write_text("def leaked():\n", encoding="utf-8")
    facade, _ = make_facade(tmp_path, {"leaked": [{"name": "leaked", "file": str(outside)}]})

    with pytest.raises(FacadeError) as raised:
        facade.focus_symbol(SymbolFocusRequest(repo_id="demo", query="leaked"))

    assert raised.value.code == "SYMBOL_NOT_FOUND"


def test_focus_symbol_reports_active_index_as_not_ready(tmp_path: Path) -> None:
    indexer = FakeIndexer(tmp_path)
    facade = BoosterFacade(
        indexer,
        RepositoryAllowlist({"demo": tmp_path}),
        status_provider=lambda: {"active": {str(tmp_path.resolve()): {"status": "running"}}},
    )

    with pytest.raises(FacadeError) as raised:
        facade.focus_symbol(SymbolFocusRequest(repo_id="demo", query="pending"))

    assert raised.value.code == "INDEX_NOT_READY"
    assert raised.value.retryable is True


def test_search_reuses_hybrid_results_and_normalizes_files(tmp_path: Path) -> None:
    first = tmp_path / "indexer.py"
    second = tmp_path / "server.py"
    first.write_text("def first():\n", encoding="utf-8")
    second.write_text("def second():\n", encoding="utf-8")
    outside = tmp_path.parent / "outside.py"
    outside.write_text("def outside():\n", encoding="utf-8")
    indexer = FakeIndexer(tmp_path)
    facade = BoosterFacade(
        indexer,
        RepositoryAllowlist({"demo": tmp_path}),
        search_lookup=lambda query, limit: [
            {"file": str(first), "symbol": "first", "retrieval": {"score": 0.8}},
            {"file": str(first), "retrieval": {"score": 0.4}},
            {"file": str(second), "kind": "module", "score": 0.2},
            {"file": str(outside), "retrieval": {"score": 1.0}},
        ][:limit],
    )

    result = facade.search(SearchRequest(repo_id="demo", query="repository", limit=8))

    assert [match.path for match in result.result.matches] == ["indexer.py", "server.py"]
    assert result.result.matches[0].score == 0.8
    assert result.ui.highlights == ["indexer.py", "server.py"]
    assert result.ui.mode == "search"


def test_search_normalizes_index_not_ready_error(tmp_path: Path) -> None:
    facade = BoosterFacade(
        FakeIndexer(tmp_path),
        RepositoryAllowlist({"demo": tmp_path}),
        search_lookup=lambda _query, _limit: (_ for _ in ()).throw(
            RuntimeError("Индекс ещё строится")
        ),
    )

    with pytest.raises(FacadeError) as raised:
        facade.search(SearchRequest(repo_id="demo", query="pending"))

    assert raised.value.code == "INDEX_NOT_READY"


def test_impact_reuses_cognitive_runtime_and_normalizes_paths(tmp_path: Path) -> None:
    target = tmp_path / "service.py"
    caller = tmp_path / "controller.py"
    test_file = tmp_path / "tests" / "test_service.py"
    test_file.parent.mkdir()
    for path in (target, caller, test_file):
        path.write_text("def value():\n", encoding="utf-8")
    outside = tmp_path.parent / "outside.py"
    outside.write_text("def outside():\n", encoding="utf-8")
    calls: list[tuple[str, str, int]] = []

    def impact_lookup(target_name: str, repo: str, max_depth: int) -> dict[str, object]:
        calls.append((target_name, repo, max_depth))
        return {
            "target": target_name,
            "matches": [{"name": target_name, "file": str(target), "start": 0}],
            "affected_files": [str(target), str(caller), str(outside)],
            "direct_callers": ["controller"],
            "direct_callees": ["repository"],
            "suggested_tests": [str(test_file), str(outside)],
            "risk": {"level": "medium", "score": 12},
            "knowledge_graph": {
                "edges": [{"from": "controller", "to": "service", "type": "CALLS"}]
            },
        }

    indexer = FakeIndexer(tmp_path)
    indexer.symbols = {
        str(caller): [{"name": "controller"}],
        str(target): [{"name": "service"}],
    }
    facade = BoosterFacade(
        indexer,
        RepositoryAllowlist({"demo": tmp_path}),
        impact_lookup=impact_lookup,
    )
    result = facade.impact(ImpactRequest(repo_id="demo", target="service", max_depth=2))

    assert calls == [("service", str(tmp_path.resolve()), 2)]
    assert result.result.target_file == "service.py"
    assert result.result.affected_files == ["service.py", "controller.py"]
    assert result.result.tests == ["tests/test_service.py"]
    assert result.result.callers == ["controller"]
    assert [connection.model_dump() for connection in result.result.connections] == [
        {"source": "controller.py", "target": "service.py", "type": "CALLS"}
    ]
    assert result.result.risk is not None
    assert result.result.risk.score == 12
    assert result.ui.focus is not None
    assert result.ui.focus.path == "service.py"


def test_impact_rejects_path_traversal_target(tmp_path: Path) -> None:
    facade = BoosterFacade(
        FakeIndexer(tmp_path),
        RepositoryAllowlist({"demo": tmp_path}),
        impact_lookup=lambda *_args: {},
    )

    with pytest.raises(FacadeError) as raised:
        facade.impact(ImpactRequest(repo_id="demo", target="../outside.py"))

    assert raised.value.code == "INVALID_ARGUMENT"


def test_explain_history_normalizes_existing_git_intelligence(tmp_path: Path) -> None:
    source = tmp_path / "service.py"
    source.write_text("def service():\n", encoding="utf-8")
    calls: list[tuple[str | None, str | None, str, int]] = []

    def history_lookup(path, symbol, repo, limit):
        calls.append((path, symbol, repo, limit))
        return {
            "path": str(source),
            "symbol": symbol,
            "commits": [
                {
                    "hash": "a" * 40,
                    "short_hash": "a" * 12,
                    "author": "Test",
                    "date": "2026-01-01T00:00:00+00:00",
                    "message": "Initial service",
                }
            ],
            "blame": [
                {
                    "hash": "b" * 40,
                    "short_hash": "b" * 12,
                    "author": "Test",
                    "summary": "Add service",
                    "sample_line": "def service():",
                }
            ],
            "history_hint": "Nearest change context",
        }

    facade = BoosterFacade(
        FakeIndexer(tmp_path),
        RepositoryAllowlist({"demo": tmp_path}),
        history_lookup=history_lookup,
    )
    result = facade.explain_history(HistoryRequest(repo_id="demo", path="service.py", limit=8))

    assert calls == [("service.py", None, str(tmp_path.resolve()), 8)]
    assert result.result.path == "service.py"
    assert result.result.commits[0].short_hash == "a" * 12
    assert result.result.blame[0].sample_line == "def service():"
    assert result.ui.focus is not None
    assert result.ui.focus.path == "service.py"


def test_show_diagnostics_is_read_only_and_normalizes_findings(tmp_path: Path) -> None:
    source = tmp_path / "service.py"
    source.write_text("def service():\n", encoding="utf-8")
    calls: list[tuple[list[str], str, bool, bool, int]] = []

    def diagnostics_lookup(paths, repo, include_security, run_external, timeout):
        calls.append((paths, repo, include_security, run_external, timeout))
        return {
            "paths_checked": paths,
            "summary": {"status": "failed", "total": 1, "by_severity": {"error": 1}},
            "findings": [
                {
                    "source": "py_compile",
                    "severity": "error",
                    "file": str(source),
                    "line": 1,
                    "column": 4,
                    "message": "bad syntax",
                    "rule": "python_syntax_error",
                },
                {"file": str(tmp_path.parent / "outside.py"), "message": "hidden"},
            ],
        }

    facade = BoosterFacade(
        FakeIndexer(tmp_path),
        RepositoryAllowlist({"demo": tmp_path}),
        diagnostics_lookup=diagnostics_lookup,
    )
    result = facade.show_diagnostics(DiagnosticsRequest(repo_id="demo", paths=["service.py"]))

    assert calls == [([str(source.resolve())], str(tmp_path.resolve()), False, False, 30)]
    assert result.result.paths_checked == ["service.py"]
    assert result.result.summary.status == "failed"
    assert [item.file for item in result.result.findings] == ["service.py"]
    assert result.ui.highlights == ["service.py"]


def test_find_related_tests_deduplicates_and_ranks_existing_impact_candidates(
    tmp_path: Path,
) -> None:
    test_by_name = tmp_path / "tests" / "test_service.py"
    test_by_import = tmp_path / "tests" / "test_controller.py"
    test_by_name.parent.mkdir()
    test_by_name.write_text("", encoding="utf-8")
    test_by_import.write_text("", encoding="utf-8")
    facade = BoosterFacade(
        FakeIndexer(tmp_path),
        RepositoryAllowlist({"demo": tmp_path}),
        impact_lookup=lambda *_args: {
            "suggested_tests": [str(test_by_name), str(test_by_name)],
            "import_hits": [{"file": str(test_by_import)}],
        },
    )

    result = facade.find_related_tests(
        RelatedTestsRequest(repo_id="demo", target="service", limit=8)
    )

    assert [item.model_dump() for item in result.result.tests] == [
        {"path": "tests/test_controller.py", "relation": "import"},
        {"path": "tests/test_service.py", "relation": "name"},
    ]
    assert result.ui.highlights == ["tests/test_controller.py", "tests/test_service.py"]


def test_read_only_cache_is_scoped_by_generation(tmp_path: Path) -> None:
    class ChangingIndexer(FakeIndexer):
        generation_id = "generation-one"

        def index_health(self) -> dict[str, object]:
            return {
                "repository": str(self.root),
                "generation_id": self.generation_id,
                "ready": True,
            }

    indexer = ChangingIndexer(tmp_path)
    calls = 0

    def search_lookup(_query: str, _limit: int) -> list[dict[str, object]]:
        nonlocal calls
        calls += 1
        return [{"file": str(tmp_path / "service.py"), "score": float(calls)}]

    facade = BoosterFacade(
        indexer,
        RepositoryAllowlist({"demo": tmp_path}),
        search_lookup=search_lookup,
        cache=ReadOnlyCache(max_entries=4, ttl_seconds=60),
    )
    request = SearchRequest(repo_id="demo", query="service")

    first = facade.search_code(request)
    second = facade.search_code(request)
    indexer.generation_id = "generation-two"
    third = facade.search_code(request)

    assert calls == 2
    assert first.result.matches[0].score == second.result.matches[0].score == 1.0
    assert third.result.matches[0].score == 2.0
