"""Явный alias provider module для интеграций, ожидающих `upstream.client`."""

from .provider import OpenAICompatibleProvider, UpstreamProvider

__all__ = ["OpenAICompatibleProvider", "UpstreamProvider"]
