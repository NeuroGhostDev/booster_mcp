from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from booster_web.app import create_app
from booster_web.facade import BoosterFacade, FacadeError
from booster_web.models import SnapshotCompareRequest
from booster_web.security import RepositoryAllowlist
from repository_lifecycle import RepositorySnapshotStore


class Indexer:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def index_health(self) -> dict[str, object]:
        return {"repository": str(self.root), "ready": True, "generation_id": "generation"}

    def stats(self) -> dict[str, object]:
        return {"generation_id": "generation", "vectors_in_faiss": 1}


def write_report(path: Path, manifest: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "file_manifest": manifest}),
        encoding="utf-8",
    )


def content_hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def test_compare_snapshots_uses_real_immutable_snapshot_store(tmp_path: Path) -> None:
    artifacts = tmp_path / ".agents" / "booster"
    report = artifacts / "scan_report.json"
    write_report(
        report,
        {
            "stable.py": {"size_bytes": 10, "mtime_ns": 1, "sha256": content_hash(b"stable-001")},
            "changed.py": {"size_bytes": 10, "mtime_ns": 1, "sha256": content_hash(b"old-value!")},
            "removed.py": {"size_bytes": 10, "mtime_ns": 1, "sha256": content_hash(b"removed!!!")},
        },
    )
    store = RepositorySnapshotStore(tmp_path)
    first = store.capture(task_id="first", reason="test")
    write_report(
        report,
        {
            "stable.py": {"size_bytes": 10, "mtime_ns": 999, "sha256": content_hash(b"stable-001")},
            "changed.py": {"size_bytes": 10, "mtime_ns": 2, "sha256": content_hash(b"new-value!")},
            "added.py": {"size_bytes": 10, "mtime_ns": 2, "sha256": content_hash(b"added-001!")},
        },
    )
    second = store.capture(task_id="second", reason="test")
    facade = BoosterFacade(
        Indexer(tmp_path),
        RepositoryAllowlist({"demo": tmp_path}),
        snapshot_factory=lambda _root: store,
    )

    result = facade.compare_snapshots(
        SnapshotCompareRequest(
            repo_id="demo", from_id=first["snapshot_id"], to_id=second["snapshot_id"]
        )
    )

    assert result.result.added == ["added.py"]
    assert result.result.removed == ["removed.py"]
    assert result.result.changed == ["changed.py"]
    assert result.result.stable == ["stable.py"]
    assert result.result.summary == {
        "added": 1,
        "removed": 1,
        "changed": 1,
        "stable": 1,
        "unverified": 0,
    }
    assert result.ui.highlights == ["added.py", "changed.py"]


def test_compare_snapshots_detects_same_size_content_change(tmp_path: Path) -> None:
    store = RepositorySnapshotStore(tmp_path)
    report = tmp_path / ".agents" / "booster" / "scan_report.json"
    write_report(report, {"same.py": {"size_bytes": 10, "sha256": content_hash(b"old-value!")}})
    first = store.capture(task_id="same-size-first", reason="test")
    write_report(report, {"same.py": {"size_bytes": 10, "sha256": content_hash(b"new-value!")}})
    second = store.capture(task_id="same-size-second", reason="test")
    facade = BoosterFacade(
        Indexer(tmp_path),
        RepositoryAllowlist({"demo": tmp_path}),
        snapshot_factory=lambda _root: store,
    )

    result = facade.compare_snapshots(
        SnapshotCompareRequest(
            repo_id="demo", from_id=first["snapshot_id"], to_id=second["snapshot_id"]
        )
    )

    assert result.result.changed == ["same.py"]
    assert result.result.stable == []
    assert result.result.unverified == []


def test_legacy_snapshot_manifest_is_reported_as_unverified(tmp_path: Path) -> None:
    store = RepositorySnapshotStore(tmp_path)
    report = tmp_path / ".agents" / "booster" / "scan_report.json"
    write_report(report, {"legacy.py": {"size_bytes": 10, "mtime_ns": 1}})
    first = store.capture(task_id="legacy-first", reason="test")
    write_report(report, {"legacy.py": {"size_bytes": 11, "mtime_ns": 2}})
    second = store.capture(task_id="legacy-second", reason="test")
    facade = BoosterFacade(
        Indexer(tmp_path),
        RepositoryAllowlist({"demo": tmp_path}),
        snapshot_factory=lambda _root: store,
    )

    result = facade.compare_snapshots(
        SnapshotCompareRequest(
            repo_id="demo", from_id=first["snapshot_id"], to_id=second["snapshot_id"]
        )
    )

    assert result.result.changed == []
    assert result.result.stable == []
    assert result.result.unverified == ["legacy.py"]


def test_compare_snapshots_rejects_unknown_snapshot(tmp_path: Path) -> None:
    facade = BoosterFacade(
        Indexer(tmp_path),
        RepositoryAllowlist({"demo": tmp_path}),
        snapshot_factory=lambda _root: RepositorySnapshotStore(tmp_path),
    )

    with pytest.raises(FacadeError) as raised:
        facade.compare_snapshots(
            SnapshotCompareRequest(repo_id="demo", from_id="missing-a", to_id="missing-b")
        )

    assert raised.value.code == "SNAPSHOT_NOT_FOUND"


def test_snapshot_list_and_compare_api_use_logical_ids(tmp_path: Path) -> None:
    first_dir = tmp_path / ".agents" / "booster" / "snapshots" / "first"
    second_dir = tmp_path / ".agents" / "booster" / "snapshots" / "second"
    write_report(first_dir / "scan_report.json", {"old.py": {"size_bytes": 1}})
    write_report(second_dir / "scan_report.json", {"new.py": {"size_bytes": 2}})
    records = [
        {"snapshot_id": "first", "snapshot_dir": str(first_dir), "commit_short": "abc"},
        {"snapshot_id": "second", "snapshot_dir": str(second_dir), "commit_short": "def"},
    ]

    class Store:
        def list_snapshots(self, limit: int = 20):
            return records[:limit]

        def latest(self):
            return records[-1]

    facade = BoosterFacade(
        Indexer(tmp_path),
        RepositoryAllowlist({"demo": tmp_path}),
        snapshot_factory=lambda _root: Store(),
    )
    with TestClient(create_app(facade=facade)) as client:
        listing = client.get("/api/v1/snapshots", params={"repo_id": "demo"})
        comparison = client.post(
            "/api/v1/snapshots/compare",
            json={"repo_id": "demo", "from": "first", "to": "second"},
        )

    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["result"]["snapshots"]] == ["first", "second"]
    assert comparison.status_code == 200
    assert comparison.json()["result"]["from"]["id"] == "first"
    assert comparison.json()["result"]["to"]["id"] == "second"
    assert comparison.json()["result"]["added"] == ["new.py"]
    assert comparison.json()["result"]["removed"] == ["old.py"]
