"""Application factory and local launcher for Booster Observatory."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from repository_lifecycle import RepositorySnapshotStore

from .api import create_router
from .facade import BoosterFacade
from .models import ApiError, ApiResponse
from .security import RepositoryAllowlist, WebRequestGuard, WebSecuritySettings


def _project_repo_id(root: Path) -> str:
    configured = os.getenv("BOOSTER_WEB_REPO_ID")
    if configured:
        return configured
    if root.name.lower() in {"booster", "booster_mcp", "booster-mcp"}:
        return "booster-demo"
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", root.name).strip("-._") or "repo"
    return value if value[0].isalnum() else f"repo-{value}"


def _read_demo_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Prepared demo {label} is missing or invalid") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Prepared demo {label} is invalid")
    return value


def _default_facade(
    project: str | Path | None,
    mode: str | None,
    demo_dir: str | Path | None,
) -> BoosterFacade:
    # Importing server here keeps the lightweight facade independently testable
    # and reuses the process-local MCP runtime when the web app is launched.
    import server

    mode = mode or os.getenv("BOOSTER_WEB_MODE", "local")
    city_artifact_dir = None
    snapshot_factory = RepositorySnapshotStore
    snapshot_artifacts_dir = None
    precomputed_history: dict[str, object] | None = None
    precomputed_diagnostics: dict[str, object] | None = None
    if mode == "demo":
        root = Path(project or ".").expanduser().resolve()
        demo_path = Path(demo_dir).expanduser().resolve() if demo_dir is not None else root / "demo"
        if not demo_path.is_relative_to(root):
            raise ValueError("Demo directory must stay inside the project")
        manifest_path = demo_path / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Demo manifest is missing or invalid; run prepare-demo first") from exc
        if not isinstance(manifest, dict) or not manifest.get("read_only"):
            raise ValueError("Demo manifest is not a read-only prepared bundle")
        repo_id = manifest.get("repo_id")
        if not isinstance(repo_id, str):
            raise ValueError("Demo manifest has no repository ID")
        precomputed_history = _read_demo_object(demo_path / "history.json", "history")
        precomputed_diagnostics = _read_demo_object(demo_path / "diagnostics.json", "diagnostics")
        server.indexer.repos[:] = [str(root)]
        server.cognitive_runtime.repos[:] = [str(root)]
        try:
            server.indexer.load_state(demo_path / "index_state", root)
        except ValueError as exc:
            raise ValueError("Prepared demo index state is invalid") from exc
        repositories = RepositoryAllowlist({repo_id: root}, default_repo_id=repo_id)
        city_artifact_dir = demo_path

        def demo_snapshot_factory(_root: Path) -> RepositorySnapshotStore:
            return RepositorySnapshotStore(_root, artifacts_dir=demo_path)

        snapshot_factory = demo_snapshot_factory
        snapshot_artifacts_dir = demo_path
    elif project is not None:
        root = Path(project).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"Project directory does not exist: {root}")
        server.repository_registry.add(root)
        normalized = str(root)
        if normalized not in server.indexer.repos:
            server.indexer.repos.append(normalized)
        repo_id = _project_repo_id(root)
        repositories = RepositoryAllowlist({repo_id: root}, default_repo_id=repo_id)
        if not server._index_state().get("active", {}).get(normalized):
            health = server.indexer.index_health()
            if health.get("repository") != normalized or not health.get("ready"):
                server._start_index_repo_job(normalized, reason="web_startup")
    else:
        server._sync_registered_repos()
        repositories = RepositoryAllowlist(registry=server.repository_registry)

    return BoosterFacade(
        server.indexer,
        repositories,
        repository_registry=None if mode == "demo" else server.repository_registry,
        symbol_lookup=server.find_symbol,
        search_lookup=server.hybrid_search,
        impact_lookup=server.cognitive_runtime.impact_analysis,
        history_lookup=server.cognitive_runtime.git_intelligence,
        diagnostics_lookup=server.cognitive_runtime.collect_diagnostics,
        status_provider=server._index_state,
        mode=mode,
        city_artifact_dir=city_artifact_dir,
        snapshot_factory=snapshot_factory,
        snapshot_artifacts_dir=snapshot_artifacts_dir,
        precomputed_history=precomputed_history if mode == "demo" else None,
        precomputed_diagnostics=precomputed_diagnostics if mode == "demo" else None,
    )


def create_app(
    facade: BoosterFacade | None = None,
    *,
    project: str | Path | None = None,
    mode: str | None = None,
    static_dir: str | Path | None = None,
    security: WebSecuritySettings | None = None,
    demo_dir: str | Path | None = None,
) -> FastAPI:
    """Build the same-origin, read-only Observatory application."""

    if facade is None:
        facade = _default_facade(project, mode, demo_dir)
    static_root = Path(static_dir) if static_dir is not None else Path(__file__).parent / "static"
    static_root = static_root.expanduser().resolve()
    app = FastAPI(title="Booster Observatory", version="1")
    app.state.booster_facade = facade
    app.state.booster_security = WebRequestGuard(security)
    app.include_router(create_router(facade, app.state.booster_security))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        request_id = os.urandom(8).hex()
        payload = ApiResponse(
            ok=False,
            request_id=request_id,
            error=ApiError(code="INVALID_ARGUMENT", message="Invalid request", retryable=False),
        )
        return JSONResponse(status_code=400, content=payload.model_dump(exclude_none=True))

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(static_root / "index.html", media_type="text/html")

    app.mount("/static", StaticFiles(directory=static_root), name="static")
    return app


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Booster Observatory web gateway")
    parser.add_argument("--project", default=None, help="Known project directory for local launch")
    parser.add_argument("--mode", choices=("local", "demo"), default="local")
    parser.add_argument("--demo-dir", default=None, help="Prepared demo bundle directory")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


def main() -> None:
    arguments = _parse_args()
    application = create_app(
        project=arguments.project,
        mode=arguments.mode,
        demo_dir=arguments.demo_dir,
    )
    uvicorn.run(application, host=arguments.host, port=arguments.port)


if __name__ == "__main__":
    main()
