"""OpenAI-compatible HTTP provider с bounded retry и streaming."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Mapping
from typing import Any, Protocol

import httpx

from ..config import UpstreamSettings
from .models import ModelInfo, ModelList, UpstreamError


class UpstreamProvider(Protocol):
    """Контракт data plane для inference providers."""

    async def models(self) -> ModelList: ...

    async def chat_completions(self, payload: Mapping[str, Any]) -> dict[str, Any]: ...

    async def chat_completions_stream(self, payload: Mapping[str, Any]) -> AsyncIterator[bytes]: ...

    async def responses(self, payload: Mapping[str, Any]) -> dict[str, Any]: ...

    async def responses_stream(self, payload: Mapping[str, Any]) -> AsyncIterator[bytes]: ...

    async def close(self) -> None: ...


def _safe_error_text(value: Any) -> str:
    """Удаляет URL и bearer-like значения из upstream text."""
    text = str(value)
    text = re.sub(r"https?://[^\s'\"]+", "upstream", text)
    text = re.sub(r"(?i)bearer\s+[^\s,;]+", "Bearer [redacted]", text)
    text = re.sub(r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*[^\s,;]+", r"\1=[redacted]", text)
    return text[:1000]


class OpenAICompatibleProvider:
    """Провайдер LM Studio/vLLM/llama.cpp и совместимых API."""

    def __init__(
        self,
        settings: UpstreamSettings,
        client: httpx.AsyncClient,
    ) -> None:
        self.settings = settings
        self.client = client
        self.base_url = settings.base_url.rstrip("/")

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        # Ключ существует только в request headers и не попадает в модели/логи.
        return {"Authorization": f"Bearer {self.settings.api_key}"} if self.settings.api_key else {}

    async def _request_json(
        self, method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        attempts = self.settings.max_retries + 1
        for attempt in range(attempts):
            try:
                response = await self.client.request(
                    method,
                    self._url(path),
                    headers=self._headers(),
                    json=dict(payload) if payload is not None else None,
                    timeout=httpx.Timeout(
                        self.settings.read_timeout,
                        connect=self.settings.connect_timeout,
                    ),
                )
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
                if attempt + 1 < attempts:
                    await asyncio.sleep(self.settings.retry_backoff * (2**attempt))
                    continue
                raise UpstreamError("upstream connection failed", transient=True) from exc
            except httpx.HTTPError as exc:
                raise UpstreamError("upstream transport failed", transient=True) from exc

            if response.status_code >= 500 and attempt + 1 < attempts:
                await asyncio.sleep(self.settings.retry_backoff * (2**attempt))
                continue
            if response.status_code >= 400:
                try:
                    details = response.json()
                except ValueError:
                    details = None
                message = "upstream request failed"
                if isinstance(details, dict):
                    error = details.get("error", details)
                    if isinstance(error, dict) and error.get("message"):
                        message = _safe_error_text(error["message"])
                    elif isinstance(error, str):
                        message = _safe_error_text(error)
                raise UpstreamError(
                    message,
                    status_code=response.status_code,
                    details=details,
                    transient=response.status_code >= 500,
                )
            try:
                data = response.json()
            except ValueError as exc:
                raise UpstreamError(
                    "upstream returned invalid JSON", status_code=response.status_code
                ) from exc
            if not isinstance(data, dict):
                raise UpstreamError("upstream returned a non-object JSON response")
            return data
        raise UpstreamError("upstream request exhausted retry budget", transient=True)

    async def models(self) -> ModelList:
        data = await self._request_json("GET", "models")
        entries = data.get("data", [])
        models = [ModelInfo.model_validate(item) for item in entries if isinstance(item, dict)]
        return ModelList.model_validate({**data, "data": models})

    async def chat_completions(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return await self._request_json("POST", "chat/completions", payload)

    async def responses(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return await self._request_json("POST", "responses", payload)

    async def _stream(self, path: str, payload: Mapping[str, Any]) -> AsyncIterator[bytes]:
        try:
            request = self.client.build_request(
                "POST",
                self._url(path),
                headers=self._headers(),
                json=dict(payload),
                timeout=httpx.Timeout(
                    self.settings.read_timeout, connect=self.settings.connect_timeout
                ),
            )
            response = await self.client.send(request, stream=True)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            raise UpstreamError("upstream stream connection failed", transient=True) from exc
        except httpx.HTTPError as exc:
            raise UpstreamError("upstream stream transport failed", transient=True) from exc

        if response.status_code >= 400:
            try:
                body = await response.aread()
                details = json.loads(body.decode("utf-8", errors="replace"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                details = None
            finally:
                await response.aclose()
            message = "upstream stream request failed"
            if isinstance(details, dict):
                error = details.get("error", details)
                if isinstance(error, dict) and error.get("message"):
                    message = _safe_error_text(error["message"])
            raise UpstreamError(message, status_code=response.status_code, details=details)

        try:
            async for chunk in response.aiter_raw():
                yield chunk
        finally:
            await response.aclose()

    async def chat_completions_stream(self, payload: Mapping[str, Any]) -> AsyncIterator[bytes]:
        return self._stream("chat/completions", payload)

    async def responses_stream(self, payload: Mapping[str, Any]) -> AsyncIterator[bytes]:
        return self._stream("responses", payload)

    async def close(self) -> None:
        """Закрытие управляется runtime; shared client здесь не закрывается."""
