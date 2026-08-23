import pytest

from booster_home.context.budget import ContextBudgetError, ContextBudgetManager


def test_budget_uses_minimum_physical_and_configured_window() -> None:
    manager = ContextBudgetManager(
        physical_context_window=128000,
        configured_context_window=32768,
        reserve_output=4096,
        safety_margin=1024,
    )
    snapshot = manager.snapshot()
    assert snapshot.effective_context == 32768
    assert snapshot.input_hard_limit == 27648
    assert snapshot.soft_target is not None


def test_unknown_window_has_no_hard_limit() -> None:
    snapshot = ContextBudgetManager(configured_context_window="auto").snapshot()
    assert snapshot.known is False
    assert snapshot.input_hard_limit is None


def test_invalid_output_reserve_fails_closed() -> None:
    with pytest.raises(ContextBudgetError):
        ContextBudgetManager(context_window=4096, reserve_output=4096, safety_margin=1)
