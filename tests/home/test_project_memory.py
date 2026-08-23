import pytest

from booster_home.adapters.project_memory import ProjectMemoryAdapter
from booster_home.memory.models import Decision


class Runtime:
    def remember_project_fact(self, **kwargs):
        return {"promoted": True, **kwargs}


@pytest.mark.asyncio
async def test_only_validated_decisions_are_promoted() -> None:
    adapter = ProjectMemoryAdapter(Runtime(), ".")
    rejected = await adapter.promote_decision(
        Decision(session_id="s", statement="unverified", source="worker")
    )
    assert rejected["promoted"] is False
    accepted = await adapter.promote_decision(
        Decision(
            session_id="s",
            statement="validated rule",
            source="test",
            status="validated",
            evidence=["artifact://s/hash"],
        )
    )
    assert accepted["promoted"] is True
