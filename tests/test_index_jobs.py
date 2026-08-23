from __future__ import annotations

import threading
import time

from indexing_jobs import IndexJobManager


def test_index_job_manager_returns_before_slow_worker_and_supports_cancel() -> None:
    records: dict[str, dict[str, object]] = {}
    manager = IndexJobManager(records, threading.RLock())
    started = threading.Event()

    def worker(repo: str, job_id: str, cancel: threading.Event) -> None:
        started.set()
        manager.mark_running(repo, job_id)
        for index in range(100):
            if cancel.is_set():
                manager.finish(repo, job_id, "cancelled", cancel_requested=True)
                return
            manager.progress(repo, job_id, phase="embed", processed=index + 1, total=100)
            time.sleep(0.005)
        manager.finish(repo, job_id, "completed")

    started_at = time.perf_counter()
    job, was_started = manager.start(
        "repo", reason="test", task_id=None, worker=worker
    )
    elapsed = time.perf_counter() - started_at

    assert was_started is True
    assert elapsed < 0.25
    assert started.wait(1)
    assert manager.get(job_id=job["job_id"]) ["phase"] == "embed"

    cancelled = manager.cancel(str(job["job_id"]))
    assert cancelled is not None
    result = manager.wait(str(job["job_id"]), 2)
    assert result is not None
    assert result["status"] == "cancelled"
    assert result["cancel_requested"] is True


def test_index_job_manager_coalesces_duplicate_requests() -> None:
    records: dict[str, dict[str, object]] = {}
    manager = IndexJobManager(records, threading.RLock())
    release = threading.Event()

    def worker(repo: str, job_id: str, cancel: threading.Event) -> None:
        manager.mark_running(repo, job_id)
        release.wait(1)
        manager.finish(repo, job_id, "completed")

    first, first_started = manager.start(
        "repo", reason="first", task_id=None, worker=worker
    )
    second, second_started = manager.start(
        "repo", reason="second", task_id="task-2", worker=worker
    )

    assert first_started is True
    assert second_started is False
    assert second["job_id"] == first["job_id"]
    assert second["rerun_requested"] is True
    release.set()
    assert manager.wait(str(first["job_id"]), 2)["status"] == "completed"
