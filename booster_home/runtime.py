"""Явный dependency container и lifecycle Booster Home."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .adapters.booster import BoosterWorldModelAdapter
from .adapters.project_memory import ProjectMemoryAdapter
from .config import HomeConfig
from .context.budget import ContextBudgetManager
from .context.compiler import ContextCompiler
from .delegation import LocalDelegator
from .memory.artifact_store import ArtifactStore
from .memory.pager import MemoryPager
from .memory.session_store import SessionStore
from .models import ChatCompletionRequest, SessionContext
from .research.service import ResearchService
from .routing import ModelRouter
from .telemetry.events import EventType
from .telemetry.logging import RedactedLogger, redact_endpoint, redact_mapping
from .telemetry.metrics import MetricsRegistry
from .upstream.discovery import ModelDiscovery
from .upstream.provider import OpenAICompatibleProvider, UpstreamProvider
from .workers.cache import WorkerCache
from .workers.client import OpenAICompatibleWorkerBackend
from .workers.pool import WorkerPool


@dataclass(slots=True)
class HomeDependencies:
    """Опциональные injectable зависимости для тестов и embedded MCP tools."""

    client: httpx.AsyncClient | None = None
    provider: UpstreamProvider | None = None
    indexer: Any | None = None
    cognitive_runtime: Any | None = None
    repo_map: Any | None = None
    worker_pool: WorkerPool | None = None
    session_store: SessionStore | None = None
    artifact_store: ArtifactStore | None = None
    research: ResearchService | None = None


class HomeRuntime:
    """Один process-scoped runtime с одним shared client/pool/indexer."""

    def __init__(self, config: HomeConfig, dependencies: HomeDependencies | None = None) -> None:
        self.config = config
        self.dependencies = dependencies or HomeDependencies()
        project = config.project or Path.cwd()
        runtime_root = config.memory.root_dir or (project / ".agents" / "booster" / "runtime")
        self.runtime_root = runtime_root.expanduser().resolve()
        self.client = self.dependencies.client
        self.provider: UpstreamProvider | None = self.dependencies.provider
        self.indexer = self.dependencies.indexer
        self.cognitive_runtime = self.dependencies.cognitive_runtime
        self.repo_map = self.dependencies.repo_map
        self.session_store = self.dependencies.session_store or SessionStore(self.runtime_root)
        self.artifact_store = self.dependencies.artifact_store or ArtifactStore(
            self.runtime_root, config.memory.compression
        )
        self.pager = MemoryPager(
            self.artifact_store,
            enabled=config.effective_persistence and config.context.raw_artifacts,
        )
        self.worker_pool = self.dependencies.worker_pool
        self.router = ModelRouter(config.routing, config.workers.model or config.upstream.model)
        self.metrics = MetricsRegistry()
        self.logger = RedactedLogger(json_logs=config.home.json_logs, verbose=config.home.verbose)
        self.discovery: ModelDiscovery | None = None
        self.compiler: ContextCompiler | None = None
        self.delegator: LocalDelegator | None = None
        self.research: ResearchService | None = self.dependencies.research
        self.started = False
        self._maintenance_task: asyncio.Task[None] | None = None
        self._own_client = False
        self._world_model_warning: str | None = None

    async def start(self) -> None:
        if self.started:
            return
        if self.client is None:
            self.client = httpx.AsyncClient()
            self._own_client = True
        if self.provider is None:
            self.provider = OpenAICompatibleProvider(self.config.upstream, self.client)
        self.discovery = ModelDiscovery(
            self.provider,
            self.config.upstream.model,
            self.config.context.context_window,
            refresh_timeout_seconds=min(10.0, self.config.upstream.read_timeout),
        )
        self._ensure_legacy_bridge()
        if self.worker_pool is None:
            backend = OpenAICompatibleWorkerBackend(
                self.provider,
                self.config.workers.model or self.config.upstream.model,
                router=self.router,
                cache=WorkerCache(self.config.workers.cache_size),
                repair_attempts=self.config.workers.repair_attempts,
            )
            worker_count = self.config.workers.max_concurrency
            if worker_count == "auto":
                worker_count = max(1, min(8, os.cpu_count() or 1))
            self.worker_pool = WorkerPool(
                backend, int(worker_count), self.config.workers.timeout_seconds
            )
        world_model = BoosterWorldModelAdapter(
            self.indexer,
            self.cognitive_runtime,
            self.repo_map,
            repo=self.config.project,
        )
        project_memory = ProjectMemoryAdapter(
            self.cognitive_runtime, str(self.config.project) if self.config.project else None
        )
        self.compiler = ContextCompiler(
            policy=self.config.context.policy,
            budget_manager=ContextBudgetManager(
                configured_context_window=self.config.context.context_window,
                reserve_output=self.config.context.reserve_output,
                safety_margin=self.config.context.safety_margin,
                soft_target_ratio=self.config.context.soft_target_ratio,
                hard_target_ratio=self.config.context.hard_target_ratio,
            ),
            pager=self.pager,
            worker_pool=self.worker_pool,
            world_model=world_model,
            project_memory=project_memory,
            semantic_enabled=self.config.context.semantic_compression,
            enrichment_enabled=self.config.context.semantic_enrichment,
        )
        self.delegator = LocalDelegator(self.worker_pool, self.router)
        self.research = self.research or ResearchService(
            self.config.project or Path.cwd(),
            indexer=self.indexer,
            cognitive_runtime=self.cognitive_runtime,
            delegator=self.delegator,
            settings=self.config.research,
        )
        self.started = True
        self._maintenance_task = asyncio.create_task(
            self._maintenance_loop(), name="booster-home-maintenance"
        )

    def _ensure_legacy_bridge(self) -> None:
        """Создаёт ровно одну legacy связку, но не ломает gateway при optional deps."""
        if self.config.project is None:
            return
        if (
            self.indexer is not None
            and self.cognitive_runtime is not None
            and self.repo_map is not None
        ):
            return
        try:
            from cognitive_runtime import CognitiveRuntime
            from indexer import RepoIndexer
            from repomap import RepoMap

            project = str(self.config.project)
            if self.indexer is None:
                self.indexer = RepoIndexer([])
            if self.cognitive_runtime is None:
                self.cognitive_runtime = CognitiveRuntime(self.indexer, [project])
            if self.repo_map is None:
                self.repo_map = RepoMap(root=project)
        except Exception as exc:
            self._world_model_warning = f"legacy world model unavailable: {type(exc).__name__}"

    async def _maintenance_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.config.memory.maintenance_interval_seconds)
                await self.session_store.cleanup(self.config.memory.max_session_age_days)
        except asyncio.CancelledError:
            return

    async def resolve_session(
        self, request: ChatCompletionRequest, header_value: str | None = None
    ) -> SessionContext:
        metadata = request.model_extra or {}
        conversation = (
            metadata.get("conversation")
            if isinstance(metadata.get("conversation"), dict)
            else metadata
        )
        client = metadata.get("client") if isinstance(metadata.get("client"), dict) else metadata
        session_id = self.session_store.resolve_id(header_value, conversation, client)
        await self.session_store.set_active(session_id, True)
        context = await self.session_store.context(session_id)
        return SessionContext(
            session_id=session_id,
            metadata=context["session"].metadata,
            working_set=context["working_set"],
            recent_events=context["recent_events"],
        )

    async def event(
        self, session_id: str, event_type: str | EventType, payload: dict[str, Any], request_id: str
    ) -> None:
        safe_type = event_type.value if isinstance(event_type, EventType) else str(event_type)
        await self.session_store.append_event(session_id, safe_type, payload, request_id=request_id)

    async def status(self) -> dict[str, Any]:
        models = []
        if self.discovery is not None:
            try:
                model_list = await asyncio.wait_for(
                    self.discovery.list_models(),
                    timeout=min(10.0, self.config.upstream.read_timeout),
                )
                models = [
                    redact_mapping(item.model_dump(mode="json"))
                    for item in model_list.data
                ]
            except Exception:
                models = []
        sessions = await self.session_store.list_sessions()
        return {
            "gateway": {
                "status": "READY" if self.started else "STOPPED",
                "listen": self.config.home.listen,
                "port": self.config.home.port,
                "endpoint": f"http://{self.config.home.listen}:{self.config.home.port}/v1",
            },
            "upstream": {
                "status": "CONFIGURED" if self.provider is not None else "UNCONFIGURED",
                "endpoint": redact_endpoint(self.config.upstream.base_url),
                "model": self.config.upstream.model,
                "api_key_configured": bool(self.config.upstream.api_key),
                "models": models,
            },
            "context": {
                "policy": self.config.context.policy.value,
                "persistent_memory": self.config.effective_persistence,
                "semantic_workers": self.worker_pool.max_concurrency if self.worker_pool else 0,
                "world_model": self.indexer is not None and self.cognitive_runtime is not None,
                "warning": self._world_model_warning,
            },
            "research": {"available": self.research is not None},
            "sessions": {"count": len(sessions)},
            "metrics": self.metrics.snapshot(),
        }

    async def health(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.started else "starting",
            "upstream_configured": bool(self.config.upstream.base_url),
            "api_key_configured": bool(self.config.upstream.api_key),
        }

    async def close(self) -> None:
        if not self.started and self.client is None:
            return
        if self._maintenance_task is not None:
            self._maintenance_task.cancel()
            await asyncio.gather(self._maintenance_task, return_exceptions=True)
            self._maintenance_task = None
        if self.worker_pool is not None and self.dependencies.worker_pool is None:
            await self.worker_pool.close()
        if self.provider is not None:
            close = getattr(self.provider, "close", None)
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result
        if self.client is not None and self._own_client:
            await self.client.aclose()
        self.started = False


def build_runtime(config: HomeConfig, dependencies: HomeDependencies | None = None) -> HomeRuntime:
    """Собирает runtime без запуска event loop или HTTP server."""
    return HomeRuntime(config, dependencies)
