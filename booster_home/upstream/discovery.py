"""Обнаружение возможностей моделей без фиксированного context size."""

from __future__ import annotations

import asyncio
from typing import Any

from ..models import ModelProfile
from .models import ModelInfo, ModelList
from .provider import UpstreamProvider

SAFE_CONTEXT_WINDOW = 8192


class ModelDiscovery:
    """Сочетает runtime metadata, registry, explicit override и safe fallback."""

    def __init__(
        self,
        provider: UpstreamProvider,
        configured_model: str,
        configured_window: int | str = "auto",
        refresh_timeout_seconds: float = 10.0,
    ):
        self.provider = provider
        self.configured_model = configured_model
        self.configured_window = configured_window
        self.refresh_timeout_seconds = max(0.1, refresh_timeout_seconds)
        self._models: dict[str, ModelInfo] = {}
        self._profiles: dict[str, ModelProfile] = {}
        self._loaded = False

    async def refresh(self) -> ModelList:
        result = await self.provider.models()
        self._models = {item.id: item for item in result.data}
        self._profiles = {item.id: item.profile() for item in result.data}
        self._loaded = True
        return result

    async def list_models(self) -> ModelList:
        if not self._loaded:
            try:
                return await self.refresh()
            except Exception:
                # Gateway status должен уметь работать и при недоступном upstream.
                return ModelList(data=[])
        return ModelList(data=list(self._models.values()))

    async def profile(self, model_id: str | None = None) -> ModelProfile:
        selected = model_id or self.configured_model
        if not self._loaded:
            try:
                await asyncio.wait_for(self.refresh(), timeout=self.refresh_timeout_seconds)
            except Exception:
                pass
        profile = self._profiles.get(selected)
        explicit = self.configured_window
        if isinstance(explicit, int):
            if profile is None:
                return ModelProfile(
                    id=selected,
                    context_window=explicit,
                    source="explicit-config",
                    warning="Контекст задан явным override; upstream metadata недоступна",
                )
            return profile.model_copy(
                update={"context_window": explicit, "source": "explicit-config", "warning": None}
            )
        if profile is not None:
            return profile
        registry = _registry_profile(selected)
        if registry is not None:
            return registry
        return ModelProfile(
            id=selected,
            context_window=SAFE_CONTEXT_WINDOW,
            source="safe-fallback",
            warning=(
                "Размер контекста не подтверждён upstream metadata; использован безопасный fallback"
            ),
        )

    async def discover(self, model_id: str | None = None) -> ModelProfile:
        """Alias с говорящим именем для embedded adapters."""
        return await self.profile(model_id)


def _registry_profile(model_id: str) -> ModelProfile | None:
    """Небольшой registry содержит только проверенные capability hints."""
    known: dict[str, dict[str, Any]] = {
        "nvidia/nemotron-3-nano-4b": {
            "context_window": 32768,
            "supports_streaming": True,
            "capabilities": {"context", "diagnostics", "logs", "summarize", "classify"},
        },
    }
    data = known.get(model_id)
    if data is None:
        return None
    return ModelProfile(id=model_id, source="local-registry", **data)
