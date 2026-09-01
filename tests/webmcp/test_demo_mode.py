from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from booster_web.app import create_app
from booster_web.demo import _prepare_snapshot_pair


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def write_snapshot(demo: Path, snapshot_id: str, commit: str, report: dict[str, object]) -> None:
    directory = demo / "snapshots" / snapshot_id
    report_path = directory / "scan_report.json"
    write_json(report_path, report)
    metadata = {
        "version": 1,
        "snapshot_id": snapshot_id,
        "repository": None,
        "commit": commit,
        "commit_short": commit[:12],
        "captured_at_utc": "2026-08-28T00:00:00+00:00",
        "dirty": False,
        "snapshot_dir": str(directory),
        "artifacts": {
            "scan_report.json": {
                "path": str(report_path),
                "size_bytes": report_path.stat().st_size,
                "sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
            }
        },
        "indexed_files": 1,
    }
    write_json(directory / "metadata.json", metadata)


def make_demo_bundle(root: Path) -> Path:
    demo = root / "demo"
    source = root / "service.py"
    source.write_text("def service():\n    return True\n", encoding="utf-8")
    write_json(
        demo / "manifest.json",
        {
            "version": 1,
            "repo_id": "booster-demo",
            "read_only": True,
            "requires_indexing_on_start": False,
            "requires_embedding_model_on_start": False,
        },
    )
    write_json(
        demo / "city.json",
        {
            "repo": "",
            "buildings": [],
            "connections": [],
            "districts": {},
            "metrics": {"files": 0},
        },
    )
    (demo / "code_city.html").parent.mkdir(parents=True, exist_ok=True)
    (demo / "code_city.html").write_text("<html>prepared city</html>", encoding="utf-8")
    write_json(
        demo / "diagnostics.json",
        {
            "paths_checked": ["service.py"],
            "summary": {"status": "failed", "total": 1, "by_severity": {"error": 1}},
            "findings": [
                {
                    "source": "prepared",
                    "severity": "error",
                    "file": "service.py",
                    "line": 1,
                    "message": "prepared finding",
                }
            ],
        },
    )
    write_json(
        demo / "history.json",
        {
            "version": 1,
            "paths": {
                "service.py": {
                    "path": "service.py",
                    "commits": [
                        {
                            "hash": "a" * 40,
                            "short_hash": "a" * 12,
                            "author": "Prepared",
                            "date": "2026-01-01",
                            "message": "Prepared history",
                        }
                    ],
                    "blame": [],
                    "history_hint": "Prepared history",
                }
            },
        },
    )
    write_json(
        demo / "index_state" / "state.json",
        {"version": 1, "generation_id": "demo-generation"},
    )
    old_hash = hashlib.sha256(b"old-value!").hexdigest()
    new_hash = hashlib.sha256(b"new-value!").hexdigest()
    write_snapshot(
        demo,
        "baseline",
        "b" * 40,
        {"version": 1, "file_manifest": {"service.py": {"size_bytes": 10, "sha256": old_hash}}},
    )
    write_snapshot(
        demo,
        "current",
        "c" * 40,
        {"version": 1, "file_manifest": {"service.py": {"size_bytes": 10, "sha256": new_hash}}},
    )
    write_json(
        demo / "latest.json",
        json.loads((demo / "snapshots" / "current" / "metadata.json").read_text()),
    )
    return demo


class DemoRegistry:
    def __init__(self) -> None:
        self.add_calls = 0

    def add(self, _root: Path) -> None:
        self.add_calls += 1
        raise AssertionError("demo startup must not mutate the repository registry")


class DemoIndexer:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.repos: list[str] = []
        self.loaded: tuple[Path, Path] | None = None

    def load_state(self, directory: Path, repository: Path) -> dict[str, object]:
        self.loaded = (Path(directory), Path(repository))
        return {"version": 1, "generation_id": "demo-generation", "ready": True}

    def index_health(self) -> dict[str, object]:
        return {
            "repository": str(self.root),
            "generation_id": "demo-generation",
            "ready": True,
        }

    def stats(self) -> dict[str, object]:
        return {"generation_id": "demo-generation", "vectors_in_faiss": 1}

    def symbols_snapshot(self) -> dict[str, list[dict[str, object]]]:
        return {str(self.root / "service.py"): [{"name": "service"}]}


def test_demo_runtime_uses_only_prepared_read_only_state(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    demo = make_demo_bundle(root)
    assert not (root / ".git").exists()

    registry = DemoRegistry()
    indexer = DemoIndexer(root)

    def fail_live(*_args, **_kwargs):
        raise AssertionError("demo runtime must not call live Git or diagnostics")

    fake_server = SimpleNamespace(
        repository_registry=registry,
        indexer=indexer,
        cognitive_runtime=SimpleNamespace(
            repos=[],
            git_intelligence=fail_live,
            collect_diagnostics=fail_live,
            impact_analysis=lambda *_args: {},
        ),
        find_symbol=lambda _query: [],
        hybrid_search=lambda *_args, **_kwargs: [],
        _index_state=lambda: {},
    )
    monkeypatch.setitem(sys.modules, "server", fake_server)
    app = create_app(project=root, mode="demo", demo_dir=demo)
    before = {
        path.relative_to(demo).as_posix(): path.read_bytes()
        for path in demo.rglob("*")
        if path.is_file()
    }

    with TestClient(app) as client:
        status = client.get("/api/v1/status")
        city = client.get("/api/v1/city", params={"repo_id": "booster-demo"})
        diagnostics = client.post(
            "/api/v1/diagnostics",
            json={"repo_id": "booster-demo", "paths": ["service.py"]},
        )
        history = client.post(
            "/api/v1/history",
            json={"repo_id": "booster-demo", "path": "service.py"},
        )
        snapshots = client.get("/api/v1/snapshots", params={"repo_id": "booster-demo"})
        comparison = client.post(
            "/api/v1/snapshots/compare",
            json={"repo_id": "booster-demo", "from": "baseline", "to": "current"},
        )

    after = {
        path.relative_to(demo).as_posix(): path.read_bytes()
        for path in demo.rglob("*")
        if path.is_file()
    }
    assert registry.add_calls == 0
    assert indexer.loaded == (demo / "index_state", root)
    assert status.json()["status"] == "ready"
    assert city.json()["buildings"] == []
    assert diagnostics.status_code == 200, diagnostics.text
    assert history.status_code == 200, history.text
    assert diagnostics.json()["result"]["findings"][0]["message"] == "prepared finding"
    assert history.json()["result"]["commits"][0]["message"] == "Prepared history"
    assert {item["id"] for item in snapshots.json()["result"]["snapshots"]} == {
        "current",
        "baseline",
    }
    assert comparison.json()["result"]["changed"] == ["service.py"]
    assert before == after
    assert not (demo / ".snapshots.lock").exists()


def test_prepared_snapshot_pair_uses_real_parent_blobs(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        return
    root = tmp_path / "repository"
    root.mkdir()
    source = root / "service.py"
    source.write_text("first-val!", encoding="utf-8")
    for command in (
        ["git", "-C", str(root), "init", "-q"],
        ["git", "-C", str(root), "config", "user.email", "test@example.invalid"],
        ["git", "-C", str(root), "config", "user.name", "Test"],
        ["git", "-C", str(root), "add", "service.py"],
        ["git", "-C", str(root), "commit", "-qm", "initial"],
    ):
        subprocess.run(command, check=True, capture_output=True)
    source.write_text("old-value!", encoding="utf-8")
    for command in (
        ["git", "-C", str(root), "add", "service.py"],
        ["git", "-C", str(root), "commit", "-qm", "second"],
    ):
        subprocess.run(command, check=True, capture_output=True)
    source.write_text("new-value!", encoding="utf-8")
    report = {
        "repository": str(root),
        "summary": {"source_files_selected": 1, "inventory_files": 1, "selected_bytes": 10},
        "file_manifest": {
            "service.py": {
                "size_bytes": 10,
                "mtime_ns": 2,
                "sha256": hashlib.sha256(b"new-value!").hexdigest(),
            }
        },
    }

    pair = _prepare_snapshot_pair(root, report, root / "demo")

    assert pair is not None
    baseline = json.loads(
        (root / "demo" / "snapshots" / pair["from"] / "scan_report.json").read_text()
    )
    current = json.loads(
        (root / "demo" / "snapshots" / pair["to"] / "scan_report.json").read_text()
    )
    assert (
        baseline["file_manifest"]["service.py"]["sha256"]
        == hashlib.sha256(b"first-val!").hexdigest()
    )
    assert (
        current["file_manifest"]["service.py"]["sha256"]
        == hashlib.sha256(b"new-value!").hexdigest()
    )
