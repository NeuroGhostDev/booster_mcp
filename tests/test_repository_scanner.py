import json
from pathlib import Path

from cli import main as cli_main
from indexer import RepoIndexer
from repomap import RepoMap
from repository_scanner import RepositoryScanner, ScanConfig


def write_source(root: Path, relative_path: str, content: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_scanner_respects_ignore_rules_depth_and_size_budgets(tmp_path):
    write_source(tmp_path, "src/shallow.py", "def shallow():\n    return 1\n")
    write_source(tmp_path, "src/nested/deep.py", "def deep():\n    return 2\n")
    write_source(tmp_path, "src/large.py", "x = '" + "a" * 512 + "'\n")
    write_source(tmp_path, "ignored/skip.py", "def skip():\n    return 3\n")
    write_source(tmp_path, "node_modules/package/index.js",
                 "export const ignored = true;\n")
    (tmp_path / ".boosterignore").write_text("ignored/**\n", encoding="utf-8")

    config = ScanConfig.for_profile("quick").with_overrides(
        max_depth=1,
        max_file_bytes=128,
        max_total_bytes=512,
    )
    result = RepositoryScanner(tmp_path, config).scan()
    selected = {path.relative_to(tmp_path).as_posix() for path in result.files}

    assert selected == {"src/shallow.py"}
    assert result.selected_bytes <= config.max_total_bytes
    assert result.skipped["ignored_directory"] >= 2
    assert result.skipped["max_depth"] == 1
    assert result.skipped["max_file_bytes"] == 1


def test_cli_expand_writes_map_report_and_persistent_scan_config(tmp_path, capsys):
    write_source(tmp_path, "src/sample.py",
                 "def scan_me():\n    return True\n")

    exit_code = cli_main(
        ["expance", str(tmp_path), "--profile", "quick", "--json"])
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert result["command"] == "expand"
    assert result["source_files"] == 1
    assert Path(result["repo_map"]).read_text(
        encoding="utf-8").find("scan_me") >= 0
    assert Path(result["scan_report"]).is_file()
    assert Path(result["scan_config"]).is_file()
    assert ScanConfig.load(tmp_path).profile == "quick"


def test_repo_map_and_indexer_reuse_the_saved_scan_budget(tmp_path):
    write_source(tmp_path, "src/shallow.py", "def shallow():\n    return 1\n")
    write_source(tmp_path, "src/nested/deep.py", "def deep():\n    return 2\n")
    ScanConfig.for_profile("quick").with_overrides(max_depth=1).save(tmp_path)

    repo_map = RepoMap(tmp_path).get_repo_map()
    assert "src/shallow.py:" in repo_map
    assert "src/nested/deep.py:" not in repo_map

    indexed_files: list[str] = []
    indexer = RepoIndexer.__new__(RepoIndexer)
    indexer.repos = [str(tmp_path)]
    indexer.index_file = lambda path: indexed_files.append(
        Path(path).relative_to(tmp_path).as_posix()
    )
    indexer.on_index_complete = None

    indexer.full_index()

    assert indexed_files == ["src/shallow.py"]
