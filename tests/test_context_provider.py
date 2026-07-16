import json
from types import SimpleNamespace

from context_provider import get_repo_artifacts_status, setup_context_provider


class FakeMCP:
    def __init__(self):
        self.resources = {}
        self.tools = {}

    def resource(self, uri):
        def register(function):
            self.resources[uri] = function
            return function

        return register

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function

        return register


def test_repo_map_resource_creates_missing_cache_entry(tmp_path):
    (tmp_path / "sample.py").write_text(
        "def example_function():\n    return True\n",
        encoding="utf-8",
    )
    repo = str(tmp_path.resolve())
    mcp = FakeMCP()
    repo_maps = {}
    indexer = SimpleNamespace(repos=[repo], symbols={})

    setup_context_provider(mcp, indexer, repo_maps)

    repo_map = mcp.resources["repo://map"]()

    assert "sample.py:" in repo_map
    assert repo in repo_maps


def test_artifact_status_reports_canonical_paths(tmp_path):
    artifacts_dir = tmp_path / ".agents" / "booster"
    artifacts_dir.mkdir(parents=True)
    (artifacts_dir / "repo_map.md").write_text("sample.py:\n", encoding="utf-8")
    (artifacts_dir / "code_city.html").write_text("<html></html>", encoding="utf-8")
    (artifacts_dir / "scan_config.json").write_text("{}\n", encoding="utf-8")
    (artifacts_dir / "scan_report.json").write_text("{}\n", encoding="utf-8")

    status = get_repo_artifacts_status(tmp_path)

    assert status["artifacts"]["repo_map"]["exists"] is True
    assert status["artifacts"]["code_city"]["exists"] is True
    assert status["artifacts"]["scan_config"]["exists"] is True
    assert status["artifacts"]["scan_report"]["exists"] is True
    assert status["artifacts"]["repo_map"]["size_bytes"] > 0


def test_artifact_resource_and_tool_return_matching_status(tmp_path):
    repo = str(tmp_path.resolve())
    mcp = FakeMCP()
    indexer = SimpleNamespace(repos=[repo], symbols={})

    setup_context_provider(mcp, indexer, {})

    tool_status = mcp.tools["get_repo_artifacts"]()
    resource_status = json.loads(mcp.resources["repo://artifacts"]())

    assert tool_status["repo"] == repo
    assert resource_status["repo"] == repo
    assert set(tool_status["artifacts"]) == {
        "repo_map",
        "code_city",
        "scan_config",
        "scan_report",
    }
