from __future__ import annotations

import pytest

from booster_home.context.budget import ContextBudgetManager
from booster_home.context.compiler import ContextCompiler, ContextIntegrityError
from booster_home.memory.artifact_store import ArtifactStore
from booster_home.memory.pager import MemoryPager
from booster_home.models import ChatCompletionRequest, ModelProfile, SessionContext


@pytest.mark.asyncio
async def test_compiler_persists_evicted_raw_block(tmp_path) -> None:
    compiler = ContextCompiler(
        budget_manager=ContextBudgetManager(
            configured_context_window=128,
            reserve_output=16,
            safety_margin=8,
            soft_target_ratio=0.5,
            hard_target_ratio=0.8,
        ),
        pager=MemoryPager(ArtifactStore(tmp_path)),
    )
    request = ChatCompletionRequest(
        model="fake",
        messages=[
            {"role": "system", "content": "keep rules"},
            {"role": "user", "content": "active task"},
            {"role": "assistant", "content": "old context " * 100},
        ],
    )
    result = await compiler.compile(
        request,
        SessionContext(session_id="session"),
        ModelProfile(id="fake", context_window=128),
    )
    assert result.artifact_refs
    assert any(operation.operation == "evict" for operation in result.operations)


@pytest.mark.asyncio
async def test_compiler_fails_closed_when_persistence_is_disabled(tmp_path) -> None:
    compiler = ContextCompiler(
        budget_manager=ContextBudgetManager(
            configured_context_window=128, reserve_output=16, safety_margin=8
        ),
        pager=MemoryPager(ArtifactStore(tmp_path), enabled=False),
    )
    request = ChatCompletionRequest(
        model="fake",
        messages=[
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "task"},
            {"role": "assistant", "content": "old context " * 100},
        ],
    )
    with pytest.raises(ContextIntegrityError):
        await compiler.compile(
            request,
            SessionContext(session_id="session"),
            ModelProfile(id="fake", context_window=128),
        )
