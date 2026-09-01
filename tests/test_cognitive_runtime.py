import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cognitive_runtime import CognitiveRuntime
from graphs import Graphs


def make_runtime(tmp_path: Path) -> CognitiveRuntime:
    controller = tmp_path / "controller.py"
    service = tmp_path / "service.py"
    repository = tmp_path / "repository.py"
    controller.write_text("def controller():\n    return service()\n", encoding="utf-8")
    service.write_text("def service():\n    return repository()\n", encoding="utf-8")
    repository.write_text("def repository():\n    return 1\n", encoding="utf-8")

    graphs: Any = Graphs()
    graphs.add_call(str(controller), "controller", "service")
    graphs.add_call(str(service), "service", "repository")
    graphs.add_call(str(service), "service", "str")

    indexer: Any = SimpleNamespace(
        repos=[str(tmp_path)],
        graphs=graphs,
        symbols={
            str(controller): [
                {"name": "controller", "start": 0, "end": 1, "file": str(controller)}
            ],
            str(service): [{"name": "service", "start": 0, "end": 1, "file": str(service)}],
            str(repository): [
                {"name": "repository", "start": 0, "end": 1, "file": str(repository)}
            ],
        },
    )
    return CognitiveRuntime(indexer, indexer.repos)


def test_impact_analysis_traces_callers_and_callees(tmp_path: Path):
    runtime = make_runtime(tmp_path)

    result = runtime.impact_analysis("service", max_depth=2)

    assert result["target"] == "service"
    assert "controller" in result["direct_callers"]
    assert "repository" in result["direct_callees"]
    assert "str" in result["external_callees"]
    assert "str" not in result["affected_symbols"]
    assert result["blast_radius"]["files"] == 3
    assert result["knowledge_graph"]["storage"] == "in_memory"


def test_project_memory_recall_filters_structured_facts(tmp_path: Path):
    runtime = make_runtime(tmp_path)

    saved = runtime.remember_project_fact(
        category="architecture",
        fact="Frontend communicates with backend only through BFF",
        confidence=0.95,
        source="test",
    )
    recalled = runtime.project_memory_recall(query="BFF frontend")

    assert saved["count"] == 1
    assert recalled["facts"][0]["category"] == "architecture"
    assert "BFF" in recalled["context"]


def test_project_memory_rejects_corrupt_json_and_writes_valid_json(tmp_path: Path):
    runtime = make_runtime(tmp_path)

    saved = runtime.remember_project_fact(category="test", fact="atomic memory")
    memory_path = tmp_path / ".agents" / "booster" / "memory.json"
    assert saved["count"] == 1
    assert json.loads(memory_path.read_text(encoding="utf-8"))["_booster_project_facts"]
    assert not list(memory_path.parent.glob(f".{memory_path.name}.*"))

    memory_path.write_text("{broken", encoding="utf-8")
    with pytest.raises(RuntimeError, match="project memory повреждена"):
        runtime.project_memory_recall()


def test_collect_diagnostics_reports_python_syntax_error(tmp_path: Path):
    runtime = make_runtime(tmp_path)
    broken = tmp_path / "broken.py"
    broken.write_text("def broken(:\n    pass\n", encoding="utf-8")

    result = runtime.collect_diagnostics(
        paths=[str(broken)],
        include_security=False,
        run_external=False,
    )

    assert result["summary"]["status"] == "failed"
    assert result["commands"][0]["status"] == "failed"
    assert result["commands"][0]["command"].startswith("internal compile(")
    assert result["findings"][0]["source"] == "py_compile"
    assert result["findings"][0]["severity"] == "error"


def test_collect_diagnostics_fails_closed_on_external_tool_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    runtime = make_runtime(tmp_path)

    def fake_which(name: str) -> str | None:
        return "pyright" if name == "pyright" else None

    monkeypatch.setattr("cognitive_runtime.shutil.which", fake_which)

    def fake_run_process(
        command: object,
        cwd: Path,
        timeout_seconds: int = 120,
        shell: bool = False,
    ) -> dict[str, Any]:
        return {
            "command": "pyright --outputjson",
            "returncode": None,
            "stdout": "",
            "stderr": "Таймаут команды после 120 секунд",
            "timeout": True,
        }

    monkeypatch.setattr(runtime, "_run_process", fake_run_process)

    result = runtime.collect_diagnostics(
        paths=[str(tmp_path / "service.py")],
        include_security=False,
        run_external=True,
    )

    assert result["summary"]["status"] == "failed"
    assert result["findings"][-1]["source"] == "pyright"
    assert result["findings"][-1]["rule"] == "tool_execution_failed"
    assert result["findings"][-1]["status"] == "timeout"


def test_security_audit_reports_missing_scanners_as_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    runtime = make_runtime(tmp_path)
    monkeypatch.setattr("cognitive_runtime.shutil.which", lambda name: None)

    result = runtime.security_audit(paths=[str(tmp_path / "service.py")])

    assert result["status"] == "incomplete"
    assert {item["tool"] for item in result["skipped_tools"]} == {"bandit", "semgrep"}


def test_security_audit_keeps_high_findings_failed_when_other_scanner_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    runtime = make_runtime(tmp_path)

    def fake_which(name: str) -> str | None:
        return "bandit" if name == "bandit" else None

    def fake_run_process(
        command: object,
        cwd: Path,
        timeout_seconds: int = 120,
        shell: bool = False,
    ) -> dict[str, Any]:
        return {
            "command": "bandit -q -f json",
            "returncode": 1,
            "stdout": json.dumps(
                {
                    "results": [
                        {
                            "filename": str(tmp_path / "service.py"),
                            "line_number": 1,
                            "issue_severity": "HIGH",
                            "issue_confidence": "HIGH",
                            "issue_text": "unsafe test finding",
                            "test_id": "B999",
                        }
                    ]
                }
            ),
            "stderr": "",
        }

    monkeypatch.setattr("cognitive_runtime.shutil.which", fake_which)
    monkeypatch.setattr(runtime, "_run_process", fake_run_process)

    result = runtime.security_audit(paths=[str(tmp_path / "service.py")])

    assert result["status"] == "failed"
    assert result["findings"][0]["source"] == "bandit"
    assert result["findings"][0]["severity"] == "high"


def test_collect_diagnostics_parses_ruff_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    runtime = make_runtime(tmp_path)

    def fake_which(name: str) -> str | None:
        return "ruff" if name == "ruff" else None

    monkeypatch.setattr("cognitive_runtime.shutil.which", fake_which)

    def fake_run_process(
        command: object,
        cwd: Path,
        timeout_seconds: int = 120,
        shell: bool = False,
    ) -> dict[str, Any]:
        return {
            "command": "ruff check --output-format json",
            "returncode": 1,
            "stdout": json.dumps(
                [
                    {
                        "filename": str(tmp_path / "service.py"),
                        "location": {"row": 1, "column": 8},
                        "code": "F821",
                        "message": "Undefined name `missing_name`",
                    }
                ]
            ),
            "stderr": "",
        }

    monkeypatch.setattr(runtime, "_run_process", fake_run_process)

    result = runtime.collect_diagnostics(
        paths=[str(tmp_path / "service.py")],
        include_security=False,
        run_external=True,
    )

    ruff_findings = [finding for finding in result["findings"] if finding["source"] == "ruff"]
    assert result["summary"]["status"] == "failed"
    assert ruff_findings[0]["severity"] == "error"
    assert ruff_findings[0]["rule"] == "F821"


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_git_intelligence_reads_file_history(tmp_path: Path):
    runtime = make_runtime(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-m",
            "Initial cognitive runtime fixture",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    result = runtime.git_intelligence(path="service.py")

    assert result["commits"][0]["message"] == "Initial cognitive runtime fixture"
    assert result["history_hint"].startswith("Ближайший контекст изменения")
