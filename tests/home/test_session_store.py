from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from booster_home.memory.session_store import SessionStore


@pytest.mark.asyncio
async def test_session_resolution_and_timeline_are_isolated(tmp_path) -> None:
    store = SessionStore(tmp_path)
    assert (
        store.resolve_id("explicit", {"conversation_id": "other"}, {"client_id": "third"})
        == "explicit"
    )
    assert store.resolve_id(None, {"conversation_id": "conversation"}, None) == "conversation"
    await store.append_event("a", "REQUEST_RECEIVED", {"value": 1}, request_id="r1")
    await store.append_event("b", "REQUEST_RECEIVED", {"value": 2}, request_id="r2")
    assert (await store.read_events("a"))[0]["payload"]["value"] == 1
    assert (await store.read_events("b"))[0]["payload"]["value"] == 2


def test_session_store_serializes_writes_across_processes(tmp_path) -> None:
    script = (
        "import asyncio, sys\n"
        "from pathlib import Path\n"
        "from booster_home.memory.session_store import SessionStore\n"
        "asyncio.run(\n"
        "    SessionStore(Path(sys.argv[1])).append_event(\n"
        "        sys.argv[3], sys.argv[4], {'i': sys.argv[2]}\n"
        "    )\n"
        ")\n"
    )
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(tmp_path), str(index), "shared", "TEST"],
            cwd=Path(__file__).resolve().parents[2],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index in range(6)
    ]

    results = []
    for process in processes:
        return_code = process.wait()
        stdout, stderr = process.communicate()
        results.append((return_code, stdout, stderr))
    assert [result[0] for result in results] == [0] * len(processes), results
    timeline = tmp_path / "sessions" / "shared" / "timeline.jsonl"
    events = [json.loads(line) for line in timeline.read_text(encoding="utf-8").splitlines()]
    assert [event["seq"] for event in events] == list(range(1, len(processes) + 1))
