from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import server
from repository_scanner import RepositoryScanner


def test_server_index_job_is_background_and_waitable(tmp_path, monkeypatch) -> None:
    source = tmp_path / "main.py"
    source.write_text("def main():\n    return True\n", encoding="utf-8")
    repo = str(tmp_path.resolve())
    scan = RepositoryScanner(repo).scan()
    entered = threading.Event()

    generation = SimpleNamespace(
        generation_id="generation-test",
        base_generation_id=None,
        scan_result=scan,
    )

    def fake_build_generation(repo_path, *, cancel, progress):
        entered.set()
        progress("parse", 0, 1)
        time.sleep(0.15)
        progress("embed", 1, 1)
        return generation

    monkeypatch.setattr(server.indexer, "build_generation", fake_build_generation)
    monkeypatch.setattr(server.indexer, "promote_generation", lambda value: None)
    monkeypatch.setattr(server, "on_index_callback", lambda value: None)
    monkeypatch.setattr(server, "_ensure_watch_started", lambda: None)
    monkeypatch.setattr(
        server,
        "RepositorySnapshotStore",
        lambda value: SimpleNamespace(capture=lambda **kwargs: {"snapshot_id": "snapshot-test"}),
    )
    monkeypatch.setattr(
        server.repository_registry,
        "update",
        lambda *args, **kwargs: {"last_snapshot": {"snapshot_id": "snapshot-test"}},
    )
    monkeypatch.setattr(
        server.repository_registry,
        "get",
        lambda value: {"last_snapshot": {"snapshot_id": "snapshot-test"}},
    )

    server._index_jobs.clear()
    started_at = time.perf_counter()
    server._start_index_repo_job(repo, reason="test")
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.1
    assert entered.wait(1)
    job = server.index_status(repo_path=repo)
    assert job["job_id"].startswith("idx_")
    assert job["phase"] in {"parse", "embed"}

    result = server.wait_until_ready(job["job_id"], timeout_seconds=2)
    assert result["status"] == "completed"
    assert result["generation_id"] == "generation-test"
