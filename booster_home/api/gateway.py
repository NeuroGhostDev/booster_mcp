"""OpenAI-compatible gateway и control/status endpoints."""

from __future__ import annotations

import asyncio
import inspect
import ipaddress
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..context.compiler import ContextIntegrityError
from ..models import ChatCompletionRequest, RequestContext, ResponsesRequest, SessionContext
from ..runtime import HomeRuntime
from ..telemetry.events import EventType, validate_event
from ..telemetry.logging import redact_endpoint
from ..upstream.models import ModelInfo, ModelList, UpstreamError
from .models import (
    chat_response_to_responses,
    messages_to_responses_input,
    responses_input_to_messages,
)
from .streaming import forward_stream


def _error_payload(message: str, *, code: str, request_id: str | None = None) -> dict[str, Any]:
    return {
        "error": {
            "message": message,
            "type": "booster_error",
            "code": code,
            **({"request_id": request_id} if request_id else {}),
        }
    }


async def _await_if_needed(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _local_bind(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
        return address.is_loopback
    except ValueError:
        return value.lower() in {"localhost", "localhost.localdomain"}


def create_gateway_router(runtime: HomeRuntime) -> APIRouter:
    async def _authorize(
        authorization: str | None = Header(default=None),
        x_booster_auth: str | None = Header(default=None),
    ) -> None:
        expected = runtime.config.home.auth_token
        if expected is None and _local_bind(runtime.config.home.listen):
            return

        provided = x_booster_auth.strip() if x_booster_auth else ""
        if not provided and authorization:
            scheme, separator, candidate = authorization.partition(" ")
            if separator and scheme.lower() == "bearer":
                provided = candidate.strip()
        if not expected or not provided or not secrets.compare_digest(provided, expected):
            raise HTTPException(
                status_code=401,
                detail="Home authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

    router = APIRouter(dependencies=[Depends(_authorize)])

    async def _prepare(
        request: ChatCompletionRequest,
        session_header: str | None,
    ) -> tuple[SessionContext, dict[str, Any], str]:
        session = await runtime.resolve_session(request, session_header)
        request_context = RequestContext(session_id=session.session_id)
        await runtime.event(
            session.session_id,
            EventType.REQUEST_RECEIVED,
            {"model": request.model, "stream": request.stream},
            request_context.request_id,
        )
        if runtime.discovery is None or runtime.compiler is None or runtime.provider is None:
            raise RuntimeError("Home runtime не запущен")
        profile = await runtime.discovery.profile(request.model)
        try:
            compiled = await asyncio.wait_for(
                runtime.compiler.compile(request, session, profile),
                timeout=runtime.config.context.compiler_timeout,
            )
            payload = request.upstream_payload(compiled.messages)
            await runtime.event(
                session.session_id,
                EventType.CONTEXT_COMPILED,
                {
                    "input_tokens": compiled.original_tokens,
                    "compiled_tokens": compiled.compiled_tokens,
                    "removed_tokens": compiled.removed_tokens,
                    "retrieved_tokens": compiled.retrieved_tokens,
                    "artifact_refs": compiled.artifact_refs,
                    "fallback": compiled.fallback,
                },
                request_context.request_id,
            )
        except ContextIntegrityError:
            await runtime.session_store.set_active(session.session_id, False)
            raise
        except Exception as exc:
            try:
                budget = runtime.compiler.budget_manager.calculate(
                    profile.context_window, request.max_tokens
                )
                original_tokens = runtime.compiler.token_counter.count_messages(request.messages)
            except Exception:
                budget = None
                original_tokens = 0
            if (
                budget is not None
                and budget.input_hard_limit is not None
                and original_tokens > budget.input_hard_limit
            ):
                await runtime.session_store.set_active(session.session_id, False)
                raise ContextIntegrityError(
                    "compiler failure cannot pass through a request above hard input budget"
                ) from exc
            runtime.metrics.increment("compiler_fallback_total")
            payload = request.upstream_payload()
            await runtime.event(
                session.session_id,
                EventType.COMPILER_FALLBACK,
                {"reason": type(exc).__name__, "mode": "safe-pass-through"},
                request_context.request_id,
            )
            await runtime.session_store.set_active(session.session_id, False)
        return session, payload, request_context.request_id

    @router.get("/health")
    async def health() -> dict[str, Any]:
        result = await runtime.health()
        result["upstream_endpoint"] = redact_endpoint(runtime.config.upstream.base_url)
        return result

    @router.get("/v1/models")
    async def models() -> dict[str, Any]:
        if runtime.discovery is None:
            raise HTTPException(status_code=503, detail="Home runtime не запущен")
        try:
            result = await asyncio.wait_for(
                runtime.discovery.list_models(),
                timeout=min(10.0, runtime.config.upstream.read_timeout),
            )
        except Exception:
            result = ModelList(data=[])
        if not result.data:
            result = ModelList(
                data=[ModelInfo(id=runtime.config.upstream.model, owned_by="booster-config")]
            )
        return result.model_dump(mode="json", exclude_none=True)

    @router.get("/booster/status")
    async def status() -> dict[str, Any]:
        return await runtime.status()

    @router.post("/v1/chat/completions")
    async def chat_completions(
        request: ChatCompletionRequest,
        x_booster_session: str | None = Header(default=None),
    ) -> Any:
        if runtime.provider is None:
            raise HTTPException(status_code=503, detail="Home runtime не запущен")
        try:
            session, payload, request_id = await _prepare(request, x_booster_session)
        except ContextIntegrityError as exc:
            return JSONResponse(
                status_code=413, content=_error_payload(str(exc), code="context_integrity")
            )
        except RuntimeError as exc:
            return JSONResponse(
                status_code=503, content=_error_payload(str(exc), code="runtime_unavailable")
            )
        if request.stream:
            try:
                stream = await _await_if_needed(runtime.provider.chat_completions_stream(payload))
                if not hasattr(stream, "__aiter__"):
                    raise UpstreamError("upstream stream is not async iterable")
            except UpstreamError as exc:
                status_code = (
                    exc.status_code if exc.status_code and 400 <= exc.status_code < 600 else 502
                )
                await runtime.session_store.set_active(session.session_id, False)
                return JSONResponse(
                    status_code=status_code,
                    content=_error_payload(
                        str(exc), code=exc.code or "upstream_error", request_id=request_id
                    ),
                )

            async def complete(total: int) -> None:
                runtime.metrics.increment("stream_responses_total")
                await runtime.session_store.set_active(session.session_id, False)
                await runtime.event(
                    session.session_id,
                    EventType.MODEL_RESPONSE,
                    {"stream_bytes": total},
                    request_id,
                )

            return StreamingResponse(
                forward_stream(stream, complete),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Booster-Request": request_id},
            )
        try:
            response = await runtime.provider.chat_completions(payload)
        except UpstreamError as exc:
            status_code = (
                exc.status_code if exc.status_code and 400 <= exc.status_code < 600 else 502
            )
            await runtime.session_store.set_active(session.session_id, False)
            return JSONResponse(
                status_code=status_code,
                content=_error_payload(
                    str(exc), code=exc.code or "upstream_error", request_id=request_id
                ),
            )
        await runtime.event(
            session.session_id,
            EventType.MODEL_RESPONSE,
            {"has_usage": "usage" in response},
            request_id,
        )
        await runtime.session_store.set_active(session.session_id, False)
        return JSONResponse(content=response, headers={"X-Booster-Request": request_id})

    @router.post("/v1/responses")
    async def responses(
        request: ResponsesRequest,
        x_booster_session: str | None = Header(default=None),
    ) -> Any:
        if runtime.provider is None:
            raise HTTPException(status_code=503, detail="Home runtime не запущен")
        try:
            messages = responses_input_to_messages(request.input)
        except ValueError as exc:
            return JSONResponse(
                status_code=501,
                content=_error_payload(str(exc), code="unsupported_responses_input"),
            )
        chat_request = ChatCompletionRequest(
            model=request.model,
            messages=messages,
            stream=request.stream,
            max_tokens=request.max_output_tokens,
        )
        try:
            session, compiled_payload, request_id = await _prepare(chat_request, x_booster_session)
        except ContextIntegrityError as exc:
            return JSONResponse(
                status_code=413, content=_error_payload(str(exc), code="context_integrity")
            )
        except RuntimeError as exc:
            return JSONResponse(
                status_code=503, content=_error_payload(str(exc), code="runtime_unavailable")
        )
        response_input = compiled_payload.get("messages", messages_to_responses_input(messages))
        payload = request.upstream_payload(response_input)
        compiled_messages = compiled_payload.get("messages")
        if not isinstance(compiled_messages, list):
            compiled_messages = [
                message.model_dump(exclude_none=True) for message in messages
            ]
        if request.stream:
            try:
                responses_stream = getattr(runtime.provider, "responses_stream", None)
                if responses_stream is None:
                    raise UpstreamError("Responses streaming endpoint unavailable", status_code=404)
                stream = await _await_if_needed(responses_stream(payload))
            except UpstreamError as exc:
                if exc.status_code == 404:
                    # Некоторые локальные providers поддерживают только chat
                    # streaming. Не выполняем retry после начала stream.
                    chat_payload = request.model_dump(exclude_none=True)
                    chat_payload.pop("input", None)
                    chat_payload.pop("max_output_tokens", None)
                    chat_payload["model"] = request.model
                    chat_payload["messages"] = compiled_messages
                    chat_payload["stream"] = True
                    try:
                        stream = await _await_if_needed(
                            runtime.provider.chat_completions_stream(chat_payload)
                        )
                    except UpstreamError as fallback_exc:
                        await runtime.session_store.set_active(session.session_id, False)
                        return JSONResponse(
                            status_code=502,
                            content=_error_payload(
                                str(fallback_exc),
                                code="upstream_error",
                                request_id=request_id,
                            ),
                        )
                else:
                    status_code = (
                        exc.status_code if exc.status_code and 400 <= exc.status_code < 600 else 502
                    )
                    await runtime.session_store.set_active(session.session_id, False)
                    return JSONResponse(
                        status_code=status_code,
                        content=_error_payload(
                            str(exc), code=exc.code or "upstream_error", request_id=request_id
                        ),
                    )

            async def complete(total: int) -> None:
                await runtime.session_store.set_active(session.session_id, False)
                await runtime.event(
                    session.session_id,
                    EventType.MODEL_RESPONSE,
                    {"stream_bytes": total, "api": "responses"},
                    request_id,
                )

            return StreamingResponse(
                forward_stream(stream, complete),
                media_type="text/event-stream",
                headers={"X-Booster-Request": request_id},
            )
        try:
            response = await runtime.provider.responses(payload)
        except UpstreamError as exc:
            if exc.status_code == 404:
                # Явная compatibility translation для upstream без Responses endpoint.
                chat_payload = request.model_dump(exclude_none=True)
                chat_payload.pop("input", None)
                chat_payload.pop("max_output_tokens", None)
                chat_payload["model"] = request.model
                chat_payload["messages"] = compiled_messages
                chat_payload["stream"] = False
                try:
                    response = chat_response_to_responses(
                        await runtime.provider.chat_completions(chat_payload)
                    )
                except UpstreamError as fallback_exc:
                    await runtime.session_store.set_active(session.session_id, False)
                    return JSONResponse(
                        status_code=502,
                        content=_error_payload(
                            str(fallback_exc), code="upstream_error", request_id=request_id
                        ),
                    )
            else:
                status_code = (
                    exc.status_code if exc.status_code and 400 <= exc.status_code < 600 else 502
                )
                await runtime.session_store.set_active(session.session_id, False)
                return JSONResponse(
                    status_code=status_code,
                    content=_error_payload(
                        str(exc), code=exc.code or "upstream_error", request_id=request_id
                    ),
                )
        await runtime.event(
            session.session_id, EventType.MODEL_RESPONSE, {"api": "responses"}, request_id
        )
        await runtime.session_store.set_active(session.session_id, False)
        return JSONResponse(content=response, headers={"X-Booster-Request": request_id})

    @router.post("/booster/events")
    async def events(request: Request) -> dict[str, Any]:
        if not runtime.config.telemetry.enabled or not _local_bind(runtime.config.home.listen):
            raise HTTPException(status_code=404, detail="telemetry disabled")
        try:
            event = validate_event(await request.json())
        except Exception:
            raise HTTPException(status_code=422, detail="invalid telemetry envelope") from None
        await runtime.event(event.session_id, event.type, event.payload, event.request_id)
        runtime.metrics.increment("telemetry_events_total")
        return {
            "accepted": True,
            "type": event.type.value,
            "session_id": event.session_id,
            "request_id": event.request_id,
        }

    return router
