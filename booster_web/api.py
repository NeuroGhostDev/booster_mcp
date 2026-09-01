"""FastAPI routes for Booster Observatory."""

from __future__ import annotations

import logging
import uuid
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from .facade import BoosterFacade, FacadeError
from .models import (
    ApiError,
    ApiMeta,
    ApiResponse,
    ArchitectureRequest,
    DiagnosticsRequest,
    HistoryRequest,
    ImpactRequest,
    RelatedTestsRequest,
    SearchRequest,
    SnapshotCompareRequest,
    SymbolFocusRequest,
)
from .security import OperationTimedOut, RateLimitExceeded, WebRequestGuard

logger = logging.getLogger(__name__)


def _request_id() -> str:
    return uuid.uuid4().hex


def _error_response(error: FacadeError, request_id: str) -> JSONResponse:
    status_codes = {
        "INVALID_ARGUMENT": 400,
        "REPO_NOT_FOUND": 404,
        "SYMBOL_NOT_FOUND": 404,
        "FILE_NOT_FOUND": 404,
        "SNAPSHOT_NOT_FOUND": 404,
        "INDEX_NOT_READY": 409,
        "RATE_LIMITED": 429,
        "TIMEOUT": 504,
        "INTERNAL_ERROR": 500,
    }
    code = error.code if error.code in status_codes else "INTERNAL_ERROR"
    message = error.message if code == error.code else "Internal server error"
    payload = ApiResponse(
        ok=False,
        request_id=request_id,
        error=ApiError(
            code=code,
            message=message,
            retryable=error.retryable if code != "INTERNAL_ERROR" else False,
        ),
    )
    return JSONResponse(
        status_code=status_codes.get(code, 500),
        content=payload.model_dump(exclude_none=True),
    )


def _internal_error(request_id: str) -> JSONResponse:
    logger.exception("Booster web request failed")
    return _error_response(FacadeError("INTERNAL_ERROR", "Internal server error"), request_id)


def _success_response(request_id: str, started: float, result: Any) -> JSONResponse:
    payload = ApiResponse(
        ok=True,
        request_id=request_id,
        repo=result.repo,
        result=result.result,
        ui=result.ui,
        meta=ApiMeta(duration_ms=max(0, round((perf_counter() - started) * 1000))),
    )
    return JSONResponse(content=payload.model_dump(exclude_none=True, by_alias=True))


async def _run_guarded(request: Request, guard: WebRequestGuard, operation: Any, *args: Any) -> Any:
    client_host = request.client.host if request.client else None
    try:
        return await guard.run(client_host, operation, *args)
    except RateLimitExceeded as error:
        raise FacadeError("RATE_LIMITED", str(error), retryable=True) from error
    except OperationTimedOut as error:
        raise FacadeError("TIMEOUT", str(error), retryable=True) from error


def _check_rate(request: Request, guard: WebRequestGuard) -> None:
    try:
        guard.check_rate(request.client.host if request.client else None)
    except RateLimitExceeded as error:
        raise FacadeError("RATE_LIMITED", str(error), retryable=True) from error


def create_router(facade: BoosterFacade, guard: WebRequestGuard | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    guard = guard or WebRequestGuard()

    @router.get("/status")
    async def status(request: Request, repo_id: str | None = Query(default=None)) -> JSONResponse:
        request_id = _request_id()
        started = perf_counter()
        try:
            _check_rate(request, guard)
            result = facade.status(repo_id)
            payload = {
                "ok": True,
                "request_id": request_id,
                **result.model_dump(exclude_none=True),
                "meta": ApiMeta(
                    duration_ms=max(0, round((perf_counter() - started) * 1000))
                ).model_dump(),
            }
            return JSONResponse(content=payload)
        except FacadeError as error:
            return _error_response(error, request_id)
        except Exception:
            return _internal_error(request_id)

    @router.post("/architecture")
    async def architecture(http_request: Request, request: ArchitectureRequest) -> JSONResponse:
        request_id = _request_id()
        started = perf_counter()
        try:
            result = await _run_guarded(http_request, guard, facade.inspect_architecture, request)
            return _success_response(request_id, started, result)
        except FacadeError as error:
            return _error_response(error, request_id)
        except Exception:
            return _internal_error(request_id)

    @router.post("/symbol/focus")
    async def focus_symbol(http_request: Request, request: SymbolFocusRequest) -> JSONResponse:
        request_id = _request_id()
        started = perf_counter()
        try:
            result = await _run_guarded(http_request, guard, facade.focus_symbol, request)
            return _success_response(request_id, started, result)
        except FacadeError as error:
            return _error_response(error, request_id)
        except Exception:
            return _internal_error(request_id)

    @router.post("/search")
    async def search(http_request: Request, request: SearchRequest) -> JSONResponse:
        request_id = _request_id()
        started = perf_counter()
        try:
            result = await _run_guarded(http_request, guard, facade.search_code, request)
            return _success_response(request_id, started, result)
        except FacadeError as error:
            return _error_response(error, request_id)
        except Exception:
            return _internal_error(request_id)

    @router.post("/impact")
    async def impact(http_request: Request, request: ImpactRequest) -> JSONResponse:
        request_id = _request_id()
        started = perf_counter()
        try:
            result = await _run_guarded(http_request, guard, facade.trace_impact, request)
            return _success_response(request_id, started, result)
        except FacadeError as error:
            return _error_response(error, request_id)
        except Exception:
            return _internal_error(request_id)

    @router.post("/history")
    async def history(http_request: Request, request: HistoryRequest) -> JSONResponse:
        request_id = _request_id()
        started = perf_counter()
        try:
            result = await _run_guarded(http_request, guard, facade.explain_history, request)
            return _success_response(request_id, started, result)
        except FacadeError as error:
            return _error_response(error, request_id)
        except Exception:
            return _internal_error(request_id)

    @router.post("/diagnostics")
    async def diagnostics(http_request: Request, request: DiagnosticsRequest) -> JSONResponse:
        request_id = _request_id()
        started = perf_counter()
        try:
            result = await _run_guarded(http_request, guard, facade.show_diagnostics, request)
            return _success_response(request_id, started, result)
        except FacadeError as error:
            return _error_response(error, request_id)
        except Exception:
            return _internal_error(request_id)

    @router.post("/related-tests")
    async def related_tests(http_request: Request, request: RelatedTestsRequest) -> JSONResponse:
        request_id = _request_id()
        started = perf_counter()
        try:
            result = await _run_guarded(http_request, guard, facade.find_related_tests, request)
            return _success_response(request_id, started, result)
        except FacadeError as error:
            return _error_response(error, request_id)
        except Exception:
            return _internal_error(request_id)

    @router.get("/snapshots")
    async def snapshots(
        request: Request,
        repo_id: str = Query(min_length=1),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> JSONResponse:
        request_id = _request_id()
        started = perf_counter()
        try:
            _check_rate(request, guard)
            result = facade.list_snapshots(repo_id, limit)
            return _success_response(request_id, started, result)
        except FacadeError as error:
            return _error_response(error, request_id)
        except Exception:
            return _internal_error(request_id)

    @router.post("/snapshots/compare")
    async def compare_snapshots(
        http_request: Request, request: SnapshotCompareRequest
    ) -> JSONResponse:
        request_id = _request_id()
        started = perf_counter()
        try:
            result = await _run_guarded(http_request, guard, facade.compare_snapshots, request)
            return _success_response(request_id, started, result)
        except FacadeError as error:
            return _error_response(error, request_id)
        except Exception:
            return _internal_error(request_id)

    @router.get("/city")
    async def city(request: Request, repo_id: str = Query(min_length=1)) -> JSONResponse:
        request_id = _request_id()
        started = perf_counter()
        try:
            city_data = await _run_guarded(request, guard, facade.city_data, repo_id)
            return JSONResponse(
                content={
                    "ok": True,
                    "request_id": request_id,
                    "repo_id": repo_id,
                    "buildings": city_data.get("buildings", []),
                    "connections": city_data.get("connections", []),
                    "districts": city_data.get("districts", {}),
                    "metrics": city_data.get("metrics", {}),
                    "meta": {
                        "duration_ms": max(0, round((perf_counter() - started) * 1000)),
                        "cached": False,
                    },
                }
            )
        except FacadeError as error:
            return _error_response(error, request_id)
        except Exception:
            return _internal_error(request_id)

    @router.get("/city/html", response_model=None)
    async def city_html(
        request: Request, repo_id: str = Query(min_length=1)
    ) -> FileResponse | JSONResponse:
        request_id = _request_id()
        try:
            _check_rate(request, guard)
            city_file = facade.city_path(repo_id)
            return FileResponse(city_file, media_type="text/html")
        except FacadeError as error:
            return _error_response(error, request_id)
        except Exception:
            return _internal_error(request_id)

    return router
