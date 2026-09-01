from __future__ import annotations

import json
import socket
import threading
from pathlib import Path

import pytest
import uvicorn

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Browser, Page, sync_playwright  # noqa: E402

from booster_web.app import create_app  # noqa: E402
from booster_web.facade import BoosterFacade  # noqa: E402
from booster_web.security import RepositoryAllowlist  # noqa: E402
from repository_lifecycle import RepositorySnapshotStore  # noqa: E402


class BrowserIndexer:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.source = self.root / "indexer.py"

    def find_symbols(self, query: str) -> list[dict[str, object]]:
        if query in {"target", "RepoIndexer.target"}:
            return [{"name": query, "file": str(self.source), "start": 4}]
        return []

    def hybrid_search(self, _query: str, k: int = 8) -> list[dict[str, object]]:
        return [{"file": str(self.source), "symbol": "target", "score": 0.8}][:k]

    def impact_analysis(self, target: str, _repo: str, _max_depth: int) -> dict[str, object]:
        return {
            "target": target,
            "matches": [{"file": str(self.source)}],
            "affected_files": [str(self.source)],
            "direct_callers": ["caller"],
            "direct_callees": ["callee"],
            "suggested_tests": [str(self.root / "tests" / "test_target.py")],
            "risk": {"level": "low", "score": 1},
        }

    def git_intelligence(self, path, symbol, repo, limit):
        return {
            "path": str(self.source),
            "symbol": symbol,
            "commits": [
                {
                    "hash": "a" * 40,
                    "short_hash": "a" * 12,
                    "author": "Test",
                    "date": "2026-01-01",
                    "message": "Initial history",
                }
            ][:limit],
            "blame": [],
            "history_hint": "Initial history",
        }

    def collect_diagnostics(self, paths, repo, include_security, run_external, timeout):
        return {
            "paths_checked": paths,
            "summary": {"status": "passed", "total": 0, "by_severity": {}},
            "findings": [],
        }

    def index_health(self) -> dict[str, object]:
        return {
            "repository": str(self.root),
            "generation_id": "browser-generation",
            "ready": True,
        }

    def stats(self) -> dict[str, object]:
        return {"generation_id": "browser-generation", "vectors_in_faiss": 1}


def write_snapshot_report(path: Path, manifest: dict[str, dict[str, object]]) -> None:
    path.write_text(json.dumps({"version": 1, "file_manifest": manifest}), encoding="utf-8")


@pytest.fixture
def browser_server(tmp_path: Path):
    source = tmp_path / "indexer.py"
    source.write_text("def target():\n    return True\n", encoding="utf-8")
    city = tmp_path / ".agents" / "booster" / "code_city.html"
    city.parent.mkdir(parents=True)
    city.write_text(
        """<!doctype html><html><body><script>
window.__focused = null;
window.BoosterCity = {
  getSelection: () => window.__focused ? { path: window.__focused } : null,
  selectFile: (path) => { window.__focused = path; return true; },
  focusFile: (path) => { window.__focused = path; return true; },
  clearHighlights: () => { window.__highlights = []; return true; },
  highlightFiles: (paths) => { window.__highlights = paths; return paths.length; },
  showImpact: (result) => { window.__impact = result.target; return true; },
  showSnapshotComparison: (result) => { window.__snapshot = result.summary; return true; },
  showHistory: (result) => { window.__history = result.path; return true; },
  showDiagnostics: (result) => { window.__diagnostics = result.summary.status; return true; },
  showRelatedTests: (paths) => { window.__relatedTests = paths; return true; },
  clearSelection: () => { window.__focused = null; return true; }
};
</script>city</body></html>""",
        encoding="utf-8",
    )
    indexer = BrowserIndexer(tmp_path)
    report = tmp_path / ".agents" / "booster" / "scan_report.json"
    write_snapshot_report(report, {"stable.py": {"size_bytes": 1}, "old.py": {"size_bytes": 1}})
    snapshots = RepositorySnapshotStore(tmp_path)
    snapshots.capture(task_id="browser-first", reason="test")
    write_snapshot_report(report, {"stable.py": {"size_bytes": 1}, "new.py": {"size_bytes": 2}})
    snapshots.capture(task_id="browser-second", reason="test")
    facade = BoosterFacade(
        indexer,
        RepositoryAllowlist({"demo": tmp_path}),
        snapshot_factory=lambda _root: snapshots,
    )
    app = create_app(facade=facade)

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        threading.Event().wait(0.01)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture
def chromium():
    with sync_playwright() as playwright_instance:
        browser: Browser | None = None
        try:
            browser = playwright_instance.chromium.launch(headless=True)
        except Exception as exc:  # pragma: no cover - depends on local browser installation
            pytest.skip(f"Playwright Chromium is unavailable: {exc}")
        try:
            assert browser is not None
            yield browser
        finally:
            if browser is not None:
                browser.close()


def open_page(chromium: Browser, url: str, init_script: str | None = None) -> Page:
    page = chromium.new_page()
    if init_script:
        page.add_init_script(init_script)
    page.goto(url, wait_until="networkidle")
    return page


def test_webmcp_unavailable_keeps_ui_usable(browser_server: str, chromium: Browser) -> None:
    errors: list[str] = []
    page = chromium.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(browser_server, wait_until="networkidle")

    page.locator("#webmcp-status").wait_for()
    assert page.locator("#webmcp-status").text_content() == "UNAVAILABLE"
    assert page.locator("#city-frame").count() == 1
    assert errors == []
    page.close()


def test_webmcp_focus_updates_workspace_and_city(browser_server: str, chromium: Browser) -> None:
    page = open_page(
        chromium,
        browser_server,
        """
        window.__registeredTools = [];
        window.__registrations = [];
        document.modelContext = {
          registerTool: async (tool, options) => {
            window.__registeredTools.push(tool);
            window.__registrations.push({tool, options});
          }
        };
        """,
    )
    page.wait_for_function("() => window.__registeredTools.length === 8")

    state = page.evaluate("""async () => {
          const tool = window.__registeredTools.find(
            candidate => candidate.name === 'booster_focus_symbol'
          );
          await tool.execute({symbol: 'target'});
          return window.BoosterObservatory.workspace.getState();
        }""")
    focused = page.evaluate("() => document.querySelector('#city-frame').contentWindow.__focused")

    assert state["selectedFile"] == "indexer.py"
    assert state["generationId"] == "browser-generation"
    assert state["selectedSymbol"]["line"] == 5
    assert state["lastAgentAction"]["status"] == "completed"
    assert state["lastAgentAction"]["generation_id"] == "browser-generation"
    assert focused == "indexer.py"
    assert page.evaluate("() => window.__registeredTools.map(tool => tool.name)") == [
        "booster_focus_symbol",
        "booster_search_code",
        "booster_trace_impact",
        "booster_explain_history",
        "booster_show_diagnostics",
        "booster_find_related_tests",
        "booster_compare_snapshots",
        "booster_inspect_architecture",
        "booster_analyze_selected_file",
        "booster_history_of_selected_file",
    ]
    assert page.locator("#activity-state").text_content() == "completed"
    page.close()


def test_human_city_selection_updates_shared_workspace(
    browser_server: str, chromium: Browser
) -> None:
    page = open_page(
        chromium,
        browser_server,
        """
        window.__registeredTools = [];
        window.__registrations = [];
        document.modelContext = {
          registerTool: async (tool, options) => {
            window.__registeredTools.push(tool);
            window.__registrations.push({tool, options});
          }
        };
        """,
    )
    page.wait_for_function("() => window.BoosterObservatory")
    page.wait_for_function("() => window.__registeredTools.length === 8")

    city_frame = next(frame for frame in page.frames if frame != page.main_frame)
    city_frame.evaluate("""window.parent.postMessage(
          {type: 'booster-city-selection', path: 'indexer.py'},
          window.location.origin
        )""")

    page.wait_for_function(
        "() => window.BoosterObservatory.workspace.getState().selectedFile === 'indexer.py'"
    )
    page.wait_for_function("() => window.__registeredTools.length === 10")
    assert (
        page.evaluate("() => window.BoosterObservatory.workspace.getState().selectedFile")
        == "indexer.py"
    )
    assert (
        page.evaluate(
            "() => window.BoosterObservatory.contextual.getCurrentSelection().selectedFile"
        )
        == "indexer.py"
    )
    page.close()


def test_new_human_selection_aborts_old_contextual_tools(
    browser_server: str, chromium: Browser
) -> None:
    page = open_page(
        chromium,
        browser_server,
        """
        window.__registeredTools = [];
        window.__registrations = [];
        document.modelContext = {
          registerTool: async (tool, options) => {
            window.__registeredTools.push(tool);
            window.__registrations.push({tool, options});
          }
        };
        """,
    )
    page.wait_for_function("() => window.__registeredTools.length === 8")
    city_frame = next(frame for frame in page.frames if frame != page.main_frame)
    city_frame.evaluate("""window.parent.postMessage(
          {type: 'booster-city-selection', path: 'indexer.py'},
          window.location.origin
        )""")
    page.wait_for_function("() => window.__registeredTools.length === 10")
    city_frame.evaluate("""window.parent.postMessage(
          {type: 'booster-city-selection', path: 'server.py'},
          window.location.origin
        )""")
    page.wait_for_function("() => window.__registeredTools.length === 12")

    assert page.evaluate("() => window.__registrations[8].options.signal.aborted") is True
    assert (
        page.evaluate(
            "() => window.BoosterObservatory.contextual.getCurrentSelection().selectedFile"
        )
        == "server.py"
    )
    assert page.evaluate("() => window.BoosterObservatory.contextual.getRegisteredTools()") == [
        "booster_analyze_selected_file",
        "booster_history_of_selected_file",
    ]
    page.close()


def test_webmcp_search_and_impact_update_shared_state(
    browser_server: str, chromium: Browser
) -> None:
    page = open_page(
        chromium,
        browser_server,
        """
        window.__registeredTools = [];
        window.__registrations = [];
        document.modelContext = {
          registerTool: async (tool, options) => {
            window.__registeredTools.push(tool);
            window.__registrations.push({tool, options});
          }
        };
        """,
    )
    page.wait_for_function("() => window.__registeredTools.length === 8")
    state = page.evaluate("""async () => {
      const search = window.__registeredTools.find(tool => tool.name === 'booster_search_code');
      const impact = window.__registeredTools.find(tool => tool.name === 'booster_trace_impact');
      await search.execute({query: 'target'});
      await impact.execute({target: 'target', max_depth: 3});
      return window.BoosterObservatory.workspace.getState();
    }""")
    city_impact = page.evaluate(
        "() => document.querySelector('#city-frame').contentWindow.__impact"
    )
    city_highlights = page.evaluate(
        "() => document.querySelector('#city-frame').contentWindow.__highlights"
    )

    assert state["activeMode"] == "impact"
    assert state["highlightedFiles"] == ["indexer.py"]
    assert state["impact"]["callers"] == ["caller"]
    assert city_impact == "target"
    assert city_highlights == ["indexer.py"]
    page.close()


def test_webmcp_history_diagnostics_and_related_tests_update_state(
    browser_server: str, chromium: Browser
) -> None:
    page = open_page(
        chromium,
        browser_server,
        """
        window.__registeredTools = [];
        window.__registrations = [];
        document.modelContext = {
          registerTool: async (tool, options) => {
            window.__registeredTools.push(tool);
            window.__registrations.push({tool, options});
          }
        };
        """,
    )
    page.wait_for_function("() => window.__registeredTools.length === 8")
    state = page.evaluate("""async () => {
      const history = window.__registeredTools.find(
        tool => tool.name === 'booster_explain_history'
      );
      const diagnostics = window.__registeredTools.find(
        tool => tool.name === 'booster_show_diagnostics'
      );
      const tests = window.__registeredTools.find(
        tool => tool.name === 'booster_find_related_tests'
      );
      await history.execute({path: 'indexer.py'});
      await diagnostics.execute({paths: ['indexer.py']});
      await tests.execute({target: 'target'});
      return window.BoosterObservatory.workspace.getState();
    }""")
    city_values = page.evaluate("""() => {
      const frame = document.querySelector('#city-frame').contentWindow;
      return {
        history: frame.__history,
        diagnostics: frame.__diagnostics,
        tests: frame.__relatedTests
      };
    }""")

    assert state["activeMode"] == "tests"
    assert state["relatedTests"]["tests"][0]["path"] == "tests/test_target.py"
    assert city_values == {
        "history": "indexer.py",
        "diagnostics": "passed",
        "tests": ["tests/test_target.py"],
    }
    page.close()


def test_webmcp_snapshot_compare_updates_diff_and_city(
    browser_server: str, chromium: Browser
) -> None:
    page = open_page(
        chromium,
        browser_server,
        """
        window.__registeredTools = [];
        window.__registrations = [];
        document.modelContext = {
          registerTool: async (tool, options) => {
            window.__registeredTools.push(tool);
            window.__registrations.push({tool, options});
          }
        };
        """,
    )
    page.wait_for_function("() => window.__registeredTools.length === 8")
    page.wait_for_function(
        "() => window.BoosterObservatory.workspace.getState().snapshots.length === 2"
    )
    state = page.evaluate("""async () => {
      const workspace = window.BoosterObservatory.workspace;
      const snapshots = workspace.getState().snapshots;
      const tool = window.__registeredTools.find(
        candidate => candidate.name === 'booster_compare_snapshots'
      );
      await tool.execute({from: snapshots[1].id, to: snapshots[0].id});
      return workspace.getState();
    }""")
    city_summary = page.evaluate(
        "() => document.querySelector('#city-frame').contentWindow.__snapshot"
    )

    assert state["snapshotComparison"]["added"] == ["new.py"]
    assert state["snapshotComparison"]["removed"] == ["old.py"]
    assert state["lastAgentAction"]["status"] == "completed"
    assert city_summary["added"] == 1
    assert city_summary["removed"] == 1
    page.close()


def test_shareable_url_restores_file_selection(browser_server: str, chromium: Browser) -> None:
    page = open_page(chromium, f"{browser_server}?repo_id=demo&file=indexer.py&mode=impact")
    page.wait_for_function(
        "() => window.BoosterObservatory.workspace.getState().selectedFile === 'indexer.py'"
    )

    assert "file=indexer.py" in page.url
    assert (
        page.evaluate("() => document.querySelector('#city-frame').contentWindow.__focused")
        == "indexer.py"
    )
    page.close()
