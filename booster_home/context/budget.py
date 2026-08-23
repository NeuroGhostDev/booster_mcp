"""Расчёт input budget и adaptive soft/hard targets."""

from __future__ import annotations

from dataclasses import dataclass


class ContextBudgetError(ValueError):
    """Некорректный reserve/context configuration."""


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    effective_context: int | None
    input_hard_limit: int | None
    soft_target: int | None
    hard_target: int | None
    output_reserve: int
    safety_margin: int
    known: bool


class ContextBudgetManager:
    """Не смешивает physical window, configured override и input reserve."""

    def __init__(
        self,
        physical_context_window: int | None = None,
        configured_context_window: int | str | None = "auto",
        reserve_output: int = 4096,
        safety_margin: int = 1024,
        soft_target_ratio: float = 0.55,
        hard_target_ratio: float = 0.80,
        **aliases: object,
    ) -> None:
        if "physical_window" in aliases and physical_context_window is None:
            physical_context_window = int(aliases["physical_window"])
        if "configured_window" in aliases and configured_context_window == "auto":
            configured_context_window = aliases["configured_window"]  # type: ignore[assignment]
        if "context_window" in aliases and configured_context_window == "auto":
            configured_context_window = aliases["context_window"]  # type: ignore[assignment]
        if "output_reserve" in aliases:
            reserve_output = int(aliases["output_reserve"])
        if reserve_output <= 0 or safety_margin < 0:
            raise ContextBudgetError("reserve_output должен быть > 0, safety_margin >= 0")
        if not 0 < soft_target_ratio <= 1 or not 0 < hard_target_ratio <= 1:
            raise ContextBudgetError("target ratios должны находиться в диапазоне (0, 1]")
        if hard_target_ratio < soft_target_ratio:
            raise ContextBudgetError("hard_target_ratio не может быть меньше soft_target_ratio")
        if physical_context_window is not None and physical_context_window <= 0:
            raise ContextBudgetError("physical context window должен быть положительным")
        if configured_context_window not in (None, "auto"):
            if not isinstance(configured_context_window, int) or configured_context_window <= 0:
                raise ContextBudgetError(
                    "configured context window должен быть положительным или auto"
                )
            if reserve_output + safety_margin >= configured_context_window:
                raise ContextBudgetError(
                    "reserve_output и safety_margin превышают configured context window"
                )
        self.physical_context_window = physical_context_window
        self.configured_context_window = configured_context_window
        self.reserve_output = reserve_output
        self.safety_margin = safety_margin
        self.soft_target_ratio = soft_target_ratio
        self.hard_target_ratio = hard_target_ratio

    def calculate(
        self,
        physical_context_window: int | None = None,
        requested_output: int | None = None,
    ) -> BudgetSnapshot:
        """Совместимый явный метод расчёта budget snapshot."""
        if requested_output is None:
            return self.snapshot(physical_context_window)
        self.validate_requested_output(requested_output, physical_context_window)
        manager = ContextBudgetManager(
            physical_context_window=self.physical_context_window,
            configured_context_window=self.configured_context_window,
            reserve_output=max(self.reserve_output, requested_output),
            safety_margin=self.safety_margin,
            soft_target_ratio=self.soft_target_ratio,
            hard_target_ratio=self.hard_target_ratio,
        )
        return manager.snapshot(physical_context_window)

    def snapshot(self, physical_context_window: int | None = None) -> BudgetSnapshot:
        physical = physical_context_window or self.physical_context_window
        configured = self.configured_context_window
        if isinstance(configured, int):
            effective = min(physical, configured) if physical else configured
        else:
            effective = physical
        if effective is None:
            return BudgetSnapshot(
                None, None, None, None, self.reserve_output, self.safety_margin, False
            )
        input_limit = effective - self.reserve_output - self.safety_margin
        if input_limit <= 0:
            raise ContextBudgetError("reserve_output и safety_margin превышают context window")
        return BudgetSnapshot(
            effective_context=effective,
            input_hard_limit=input_limit,
            soft_target=max(1, int(input_limit * self.soft_target_ratio)),
            hard_target=max(1, int(input_limit * self.hard_target_ratio)),
            output_reserve=self.reserve_output,
            safety_margin=self.safety_margin,
            known=True,
        )

    def validate_requested_output(
        self, requested_output: int | None, physical_context_window: int | None = None
    ) -> None:
        if requested_output is None:
            return
        if requested_output <= 0:
            raise ContextBudgetError("requested output tokens должен быть положительным")
        snapshot = self.snapshot(physical_context_window)
        if (
            snapshot.effective_context is not None
            and requested_output + self.safety_margin >= snapshot.effective_context
        ):
            raise ContextBudgetError("requested output не оставляет input budget")
