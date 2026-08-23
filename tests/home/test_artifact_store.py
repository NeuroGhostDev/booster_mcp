from __future__ import annotations

import pytest

from booster_home.memory.artifact_store import ArtifactStore


@pytest.mark.asyncio
async def test_artifact_exact_retrieval_and_secret_redaction(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    metadata = await store.store(
        "session-a",
        "Authorization: Bearer super-secret\nline 2",
        artifact_type="terminal",
        source="test",
    )
    assert metadata.id.startswith("artifact://session-a/")
    content = await store.retrieve("session-a", metadata.id)
    assert "super-secret" not in str(content)
    assert "[REDACTED]" in str(content)
    assert "authorization" in metadata.redactions or "bearer" in metadata.redactions
    assert await store.retrieve_fragment("session-a", metadata.id, start_line=2) == "line 2"


@pytest.mark.asyncio
async def test_artifacts_are_session_isolated(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    metadata = await store.store("a", "secret", artifact_type="tool", source="test")
    with pytest.raises(PermissionError):
        await store.retrieve("b", metadata.id)


@pytest.mark.asyncio
async def test_utf8_bytes_are_redacted_before_persistence(tmp_path) -> None:
    store = ArtifactStore(tmp_path)

    metadata = await store.store(
        "session-a",
        b"api_key=byte-secret",
        artifact_type="tool",
        source="test",
    )

    content = await store.retrieve("session-a", metadata.id)
    assert "byte-secret" not in str(content)
    assert "api_key" in metadata.redactions
