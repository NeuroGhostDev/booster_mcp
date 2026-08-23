"""Прозрачный role/capability based model router."""

from __future__ import annotations

from dataclasses import dataclass

from .config import RoutingSettings


class RoutingError(RuntimeError):
    """Маршрутизация включена, но подходящая модель не найдена."""


@dataclass(frozen=True, slots=True)
class Route:
    model: str
    role: str
    matched_capabilities: frozenset[str]


class ModelRouter:
    """Выбирает только явно настроенные модели, без скрытого classifier."""

    def __init__(self, settings: RoutingSettings, default_model: str):
        self.settings = settings
        self.default_model = default_model

    def choose(self, role: str = "context", capabilities: set[str] | None = None) -> Route:
        requested = set(capabilities or ())
        if not self.settings.enabled:
            return Route(self.default_model, role, frozenset())
        for model in self.settings.models:
            if model.roles and role not in model.roles:
                continue
            if requested and not requested.issubset(model.capabilities):
                continue
            return Route(model.id, role, frozenset(requested.intersection(model.capabilities)))
        raise RoutingError(
            f"Для роли {role!r} и capabilities {sorted(requested)!r} "
            "не найдено явно настроенной модели"
        )
