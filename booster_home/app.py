"""Application factory и запуск Uvicorn без import side effects."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.gateway import create_gateway_router
from .config import HomeConfig, load_home_config
from .runtime import HomeDependencies, build_runtime


def create_app(
    config: HomeConfig | None = None, dependencies: HomeDependencies | None = None
) -> FastAPI:
    """Создаёт FastAPI app; shared resources живут в lifespan."""
    resolved = config or load_home_config()
    runtime = build_runtime(resolved, dependencies)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await runtime.start()
        app.state.home_runtime = runtime
        try:
            yield
        finally:
            await runtime.close()

    app = FastAPI(title="Booster Home", version="4.0.0", lifespan=lifespan)
    app.include_router(create_gateway_router(runtime))
    app.state.home_runtime = runtime
    return app


def run_home(
    config: HomeConfig | None = None, dependencies: HomeDependencies | None = None
) -> None:
    """Запускает только явно вызванный `booster home`."""
    import uvicorn

    resolved = config or load_home_config()
    uvicorn.run(
        create_app(resolved, dependencies),
        host=resolved.home.listen,
        port=resolved.home.port,
        log_level="debug" if resolved.home.verbose else "info",
    )
