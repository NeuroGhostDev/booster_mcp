import json
import os
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

try:
    from fastmcp import FastMCP
except ModuleNotFoundError as exc:  # pragma: no cover - exercised by wrong interpreter launches
    raise SystemExit(
        "Booster dependencies are missing from this Python interpreter. "
        "Run `uv sync --locked --extra dev` and start "
        "`.venv\\Scripts\\python.exe server.py`."
    ) from exc

import city_server
from booster_home.config import load_home_config
from booster_home.mcp import setup_home_tools
from booster_home.runtime import HomeDependencies, build_runtime
from cognitive_runtime import setup_cognitive_runtime_tools
from context7_bridge import setup_context7_bridge
from context_provider import setup_context_provider
from flipchart import setup_flipchart_tools
from indexer import IndexCancelled, RepoIndexer
from indexing_jobs import IndexJobManager
from repomap import RepoMap
from repository_lifecycle import RepositoryRegistry, RepositorySnapshotStore
from repository_scanner import RepositoryScanner
from skill_installer import auto_install_bundled_skills, install_bundled_skills, list_bundled_skills
from toolkit import setup_toolkit_tools
from visualizer import CodeCityVisualizer

# Repository bindings are shared between independently spawned MCP processes.
repository_registry = RepositoryRegistry()
_environment_repos = [r.strip() for r in os.getenv("REPOS", "").split(",") if r.strip()]


def _unique_repos(repos: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for repo in repos:
        normalized = RepositoryRegistry.normalize(repo)
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _startup_repos(environment_repos: list[str], registered_repos: list[str]) -> list[str]:
    """Scopes a bound MCP process without discarding registry persistence."""
    return _unique_repos(environment_repos if environment_repos else registered_repos)


initial_repos = _startup_repos(_environment_repos, repository_registry.list_repos())

# Callback для генерации Code City после индексации


def on_index_callback(repo_path: str) -> None:
    """Generates canonical artifacts after the repository index is updated."""
    try:
        base_dir = Path(repo_path) / ".agents" / "booster"
        base_dir.mkdir(parents=True, exist_ok=True)

        # 1. Code City
        viz = CodeCityVisualizer(indexer)
        city_output = str(base_dir / "code_city.html")
        viz.generate_visualization(repo_path, city_output)

        # 2. Repo Map
        rm = RepoMap(root=repo_path, indexer=indexer)
        architecture_map = str(cast(Any, rm).get_architecture_map())
        symbol_map = str(cast(Any, rm).get_symbol_map())
        if architecture_map:
            for map_name in ("repo_map.md", "repo_map_architecture.md"):
                (base_dir / map_name).write_text(architecture_map, encoding="utf-8")
        if symbol_map:
            (base_dir / "repo_map_symbols.md").write_text(symbol_map, encoding="utf-8")
        health = indexer.index_health() if hasattr(indexer, "index_health") else {}
        health["map_coverage"] = rm.coverage_summary()
        (base_dir / "index_health.json").write_text(
            json.dumps(health, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    except Exception as exc:
        print(f"[booster] artifact generation failed for {repo_path}: {exc}")


# The in-memory index remains process-local, while the active repository binding
# is restored from the shared registry on every MCP startup.
indexer = RepoIndexer(initial_repos, on_index_complete=on_index_callback)
repo_maps: dict[str, RepoMap] = {}  # Кэш RepoMap для каждого репозитория
_index_lock = threading.RLock()
# Serializes mutations of the process-local index without blocking status and
# registry reads on a full repository scan.
_index_work_lock = threading.RLock()
_index_jobs: dict[str, dict[str, Any]] = {}
_index_manager = IndexJobManager(_index_jobs, _index_lock)

_web_port = int(os.getenv("CITY_PORT", "8080"))
city_server.set_indexer(indexer)
_web_thread: threading.Thread | None = None

mcp = FastMCP("Booster")

# Регистрация инструментов
setup_flipchart_tools(mcp, indexer)
setup_toolkit_tools(mcp, indexer, indexer.repos)
setup_context_provider(mcp, indexer, repo_maps)
setup_context7_bridge(mcp, indexer)
cognitive_runtime = setup_cognitive_runtime_tools(mcp, indexer, indexer.repos)

# Home tools используют тот же legacy indexer и CognitiveRuntime, но сам data
# plane запускается лениво при первом control-plane вызове и не меняет MCP
# startup contract.
_home_config = load_home_config(project=initial_repos[0] if initial_repos else None)
_home_runtime = build_runtime(
    _home_config,
    HomeDependencies(
        indexer=indexer,
        cognitive_runtime=cognitive_runtime,
        repo_map=repo_maps.get(initial_repos[0]) if initial_repos else None,
    ),
)
setup_home_tools(mcp, _home_runtime)

# Инициализация visualizer
visualizer = CodeCityVisualizer(indexer)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sync_registered_repos() -> list[str]:
    """Refreshes the process-local list from the shared registry."""
    with _index_lock:
        if _environment_repos:
            # Workspace-bound MCP processes must not index repositories from
            # unrelated VS Code/Claude processes in the global registry.
            repos = _unique_repos(_environment_repos + list(indexer.repos))
        else:
            repos = _unique_repos(repository_registry.list_repos())
        indexer.repos[:] = repos
        return list(indexer.repos)


def _initialize_runtime() -> None:
    """Запускает тяжёлые legacy операции только при фактическом старте MCP."""
    _sync_registered_repos()
    auto_install_bundled_skills()
    if indexer.repos and not indexer.symbols:
        for repo in indexer.repos:
            _start_index_repo_job(repo, reason="startup")
    for repo in indexer.repos:
        repo_maps.setdefault(repo, RepoMap(root=repo))


def _start_city_web() -> None:
    """Поднимает Code City только для loopback и только при запуске MCP."""
    global _web_thread
    if _web_thread is not None and _web_thread.is_alive():
        return
    _web_thread = threading.Thread(
        target=city_server.run_server,
        kwargs={"port": _web_port, "open_browser": False, "host": "127.0.0.1"},
        daemon=True,
        name="city-web-ui",
    )
    _web_thread.start()


def _set_index_job(repo: str, **updates: Any) -> None:
    if _index_jobs is _index_manager.records:
        _index_manager.update(repo, **updates)
        return
    with _index_lock:
        current = _index_jobs.setdefault(repo, {})
        current.update(updates)
        current["updated_at_utc"] = _utc_now()


def _index_jobs_snapshot() -> dict[str, dict[str, Any]]:
    if _index_jobs is _index_manager.records:
        return _index_manager.snapshot()
    with _index_lock:
        return {
            repo: {key: value for key, value in job.items() if not key.startswith("_")}
            for repo, job in _index_jobs.items()
        }


def _registry_records_for_repos(repos: list[str]) -> list[dict[str, Any]]:
    allowed = set(repos)
    return [
        record
        for record in repository_registry.list_records()
        if record.get("repository") in allowed
    ]


def _index_state() -> dict[str, Any]:
    stats = indexer.stats() if hasattr(indexer, "stats") else {
        "files_indexed": len(indexer.symbols),
        "vectors_in_faiss": indexer.vector.index.ntotal,
    }
    jobs = _index_jobs_snapshot()
    active = {
        repo: job
        for repo, job in jobs.items()
        if job.get("status") in {"queued", "running", "cancelling"}
    }
    failed = {
        repo: job
        for repo, job in jobs.items()
        if job.get("status") == "failed"
    }
    return {"stats": stats, "jobs": jobs, "active": active, "failed": failed}


def _require_search_ready() -> None:
    state = _index_state()
    health = indexer.index_health() if hasattr(indexer, "index_health") else {}
    if health.get("ready") or state["stats"]["vectors_in_faiss"] > 0:
        return
    if state["active"]:
        raise RuntimeError(
            "Индекс ещё строится; повторите search после завершения indexing. "
            f"Состояние: {state['active']}"
        )
    if state["failed"]:
        raise RuntimeError(f"Индексирование завершилось ошибкой: {state['failed']}")


def _ensure_watch_started() -> None:
    if not indexer.repos:
        return
    def on_repository_change(repo: str) -> None:
        if hasattr(indexer, "mark_stale"):
            indexer.mark_stale("filesystem_change", repo)
        _start_index_repo_job(repo, reason="watcher_change")

    indexer.on_repository_change = on_repository_change
    city_server.ensure_watch_started(indexer)


def _index_repo_job(repo: str, job_id: str, cancel_event: threading.Event) -> None:
    rerun = False
    rerun_reason = "task_complete"
    rerun_task_id: str | None = None
    try:
        _index_manager.mark_running(repo, job_id)

        def progress(phase: str, processed: int, total: int | None) -> None:
            _index_manager.progress(repo, job_id, phase=phase, processed=processed, total=total)

        with _index_work_lock:
            generation = indexer.build_generation(
                repo,
                cancel=cancel_event.is_set,
                progress=progress,
            )
        if cancel_event.is_set():
            _index_manager.finish(repo, job_id, "cancelled", cancel_requested=True)
            return

        # Не публикуем candidate, если repo изменился во время parse/embed.
        stability_scan = RepositoryScanner(repo).scan()
        if stability_scan.file_manifest != generation.scan_result.file_manifest:
            _index_manager.finish(
                repo,
                job_id,
                "superseded",
                stale=True,
                stale_reasons=["repository_changed_during_index"],
                error="repository changed during indexing; queued a fresh generation",
            )
            rerun = True
            rerun_reason = "repository_changed"
            return

        indexer.promote_generation(generation)
        scan_report_path = generation.scan_result.save_report()
        on_index_callback(repo)
        with _index_lock:
            repo_maps[repo] = RepoMap(root=repo)
            _ensure_watch_started()
            job_context = dict(_index_jobs.get(repo, {}))
        snapshot = RepositorySnapshotStore(repo).capture(
            task_id=job_context.get("task_id"),
            reason=job_context.get("reason", "index_complete"),
            indexed_files=len(generation.scan_result.files),
        )
        health = indexer.index_health() if hasattr(indexer, "index_health") else {}
        repository_registry.update(
            repo,
            last_snapshot=snapshot,
            last_index_at_utc=_utc_now(),
            generation_id=health.get("generation_id"),
            stale=bool(health.get("stale", False)),
            completeness=health.get("map_coverage", {}),
        )
        registry_record = repository_registry.get(repo) or {}
        _index_manager.finish(
            repo,
            job_id,
            status="completed",
            files_indexed=len(generation.scan_result.files),
            generation_id=generation.generation_id,
            base_generation_id=generation.base_generation_id,
            scan_report=str(scan_report_path),
            snapshot=registry_record.get("last_snapshot"),
        )
    except IndexCancelled:
        _index_manager.finish(repo, job_id, "cancelled", cancel_requested=True)
    except Exception as exc:
        _index_manager.finish(
            repo,
            job_id,
            "failed",
            error=str(exc),
            traceback=traceback.format_exc(),
        )
    finally:
        with _index_lock:
            job = _index_jobs.get(repo, {})
            rerun = rerun or bool(job.pop("rerun_requested", False))
            if job.get("rerun_reason") is not None:
                rerun_reason = str(job.pop("rerun_reason"))
            rerun_task_id = job.pop("rerun_task_id", None)
        if rerun:
            _start_index_repo_job(repo, reason=rerun_reason, task_id=rerun_task_id)


def _start_index_repo_job(
    repo: str,
    *,
    reason: str = "add_repo",
    task_id: str | None = None,
) -> bool:
    _, started = _index_manager.start(
        repo,
        reason=reason,
        task_id=task_id,
        worker=_index_repo_job,
    )
    return started


@mcp.tool()
def semantic_search(query: str) -> list[dict[str, Any]]:
    """Ищет фрагменты кода по смыслу (векторный поиск)."""
    _require_search_ready()
    return indexer.search(query)


@mcp.tool()
def hybrid_search(query: str, k: int = 5) -> list[dict[str, Any]]:
    """Объединяет semantic-поиск и BM25 для точных символов, API и естественного языка."""
    _require_search_ready()
    return indexer.hybrid_search(query, k=k)


@mcp.tool()
def find_symbol(name: str) -> dict[str, Any]:
    """Ищет функцию или класс по имени."""
    find_symbols = getattr(indexer, "find_symbols", None)
    matches = find_symbols(name) if callable(find_symbols) else [
        sym
        for file_symbols in indexer.symbols.values()
        for sym in file_symbols
        if sym.get("name") == name
    ]

    if not matches:
        state = _index_state()
        if state["active"]:
            return {
                "error": "Индекс ещё строится; символ будет доступен после завершения indexing",
                "indexing": state["active"],
            }
        if state["failed"]:
            return {"error": "Индексирование завершилось ошибкой", "indexing": state["failed"]}
        return {"error": f"Символ '{name}' не найден"}

    return {"symbols": matches}


@mcp.tool()
def repo_stats() -> dict[str, Any]:
    """Возвращает статистику проиндексированного репозитория."""
    repos = _sync_registered_repos()
    stats = indexer.stats() if hasattr(indexer, "stats") else {
        "files_indexed": len(indexer.symbols),
        "vectors_in_faiss": indexer.vector.index.ntotal,
    }
    return {
        "repos": repos,
        **stats,
        "indexing": _index_jobs_snapshot(),
        "registry": _registry_records_for_repos(repos),
        "generation_id": indexer.index_health().get("generation_id"),
        "stale": bool(indexer.index_health().get("stale", False)),
        "completeness": indexer.index_health().get("map_coverage", {}),
    }


@mcp.tool()
def list_agent_skills() -> dict[str, Any]:
    """Возвращает список встроенных agent skills, поставляемых вместе с MCP."""
    return {
        "bundled_skills": list_bundled_skills(),
        "target_dir": str(Path.home() / ".agents" / "skills"),
    }


@mcp.tool()
def install_agent_skills(overwrite: bool = True) -> dict[str, Any]:
    """Синхронизирует встроенные agent skills в ~/.agents/skills."""
    return install_bundled_skills(overwrite=overwrite)


@mcp.tool()
def add_repo(repo_path: str, wait: bool = False) -> dict[str, Any]:
    """Добавляет репозиторий и запускает индексирование.

    По умолчанию индексирование идёт в фоне, чтобы long-running scan/embedding
    не удерживал MCP stdio request и не падал при отмене со стороны клиента.
    """
    r_path = Path(repo_path).expanduser().resolve()
    if not r_path.exists() or not r_path.is_dir():
        return {"error": f"Путь {repo_path} не существует или не является директорией"}

    repo_str = RepositoryRegistry.normalize(r_path)
    with _index_lock:
        _sync_registered_repos()
        if repo_str in indexer.repos:
            return {
                "warning": f"Репозиторий уже добавлен: {repo_str}",
                "repos": indexer.repos,
                "indexing": _index_jobs.get(repo_str, {"status": "unknown"}),
            }
        try:
            repository_registry.add(repo_str)
        except OSError as exc:
            return {"error": f"Не удалось сохранить binding репозитория: {exc}"}
        indexer.repos.append(repo_str)

    # Создание/обновление .ignore файла для отсечения мусора (node_modules, venv и т.д.)
    ignore_path = r_path / ".ignore"
    default_ignores = {
        "node_modules",
        "venv",
        ".venv",
        "env",
        ".env",
        "__pycache__",
        ".idea",
        ".vscode",
        "dist",
        "build",
        "target",
        ".next",
        ".nuxt",
        "out",
        "coverage",
        ".git",
        ".tox",
    }

    existing_ignores: set[str] = set()
    if ignore_path.exists():
        try:
            with open(ignore_path, "r", encoding="utf-8") as f:
                existing_ignores = set(line.strip() for line in f if line.strip())
        except Exception:
            pass

    new_ignores = default_ignores - existing_ignores
    if new_ignores:
        try:
            with open(ignore_path, "a", encoding="utf-8") as f:
                if existing_ignores:
                    f.write("\n")
                for item in sorted(new_ignores):
                    f.write(f"{item}\n")
        except Exception as e:
            print(f"Не удалось обновить .ignore: {e}")

    # ``wait`` остаётся в signature для совместимости, но long-running work
    # никогда не выполняется внутри MCP request.
    _start_index_repo_job(repo_str, reason="add_repo")

    base_dir = r_path / ".agents" / "booster"
    result: dict[str, Any] = {
        "success": f"Репозиторий добавлен: {repo_str}",
        "repos": list(indexer.repos),
        "files_indexed": indexer.stats()["files_indexed"],
        "indexing": _index_jobs_snapshot().get(repo_str, {"status": "unknown"}),
        "wait_deprecated": bool(wait),
        "code_city": str(base_dir / "code_city.html"),
        "repo_map": str(base_dir / "repo_map.md"),
    }

    return result


@mcp.tool()
def remove_repo(repo_path: str) -> dict[str, Any]:
    """Удаляет репозиторий из списка индексации (данные сохраняются в индексе)."""
    r_path = Path(repo_path).expanduser().resolve()
    repo_str = RepositoryRegistry.normalize(r_path)
    _sync_registered_repos()

    if repo_str not in indexer.repos:
        return {"error": f"Репозиторий не найден в списке: {repo_str}", "repos": indexer.repos}

    with _index_lock:
        job = _index_jobs.get(repo_str, {})
        if job.get("status") in {"queued", "running", "cancelling"}:
            return {
                "error": f"Репозиторий сейчас индексируется: {repo_str}",
                "indexing": dict(job),
                "repos": list(indexer.repos),
            }
        indexer.repos.remove(repo_str)
    repository_registry.remove(repo_str)
    return {"success": f"Удалён репозиторий: {repo_str}", "repos": indexer.repos}


@mcp.tool()
def reindex_repo(repo_path: str) -> dict[str, Any]:
    """Ставит полную переиндексацию в bounded background job."""
    r_path = Path(repo_path).expanduser().resolve()
    repo_str = RepositoryRegistry.normalize(r_path)
    _sync_registered_repos()

    if repo_str not in indexer.repos:
        return {"error": f"Репозиторий не в списке индексации: {repo_str}"}

    started = _start_index_repo_job(repo_str, reason="manual_reindex")
    job = _index_manager.get(repo=repo_str) or _index_jobs_snapshot().get(repo_str, {})
    base_dir = r_path / ".agents" / "booster"
    return {
        "accepted": True,
        "started": started,
        "job_id": job.get("job_id"),
        "indexing": job,
        "message": f"Переиндексация поставлена в очередь: {repo_str}",
        "code_city": str(base_dir / "code_city.html"),
        "repo_map": str(base_dir / "repo_map.md"),
        "snapshot": (repository_registry.get(repo_str) or {}).get("last_snapshot"),
    }


@mcp.tool()
def index_status(
    job_id: str | None = None,
    repo_path: str | None = None,
) -> dict[str, Any]:
    """Возвращает progress job без ожидания индексного состояния."""
    normalized = RepositoryRegistry.normalize(repo_path) if repo_path else None
    job = _index_manager.get(repo=normalized, job_id=job_id)
    if job is None:
        return {"error": "Индексирующая job не найдена", "job_id": job_id, "repository": normalized}
    health = indexer.index_health() if hasattr(indexer, "index_health") else {}
    job["ready_generation"] = health.get("generation_id")
    job["ready"] = bool(health.get("ready"))
    return job


@mcp.tool()
def cancel_index(job_id: str) -> dict[str, Any]:
    """Запрашивает cooperative cancellation на безопасной границе."""
    job = _index_manager.cancel(job_id)
    if job is None:
        return {"error": "Индексирующая job не найдена", "job_id": job_id}
    return {"accepted": True, "job": job}


@mcp.tool()
def wait_until_ready(job_id: str, timeout_seconds: float = 30.0) -> dict[str, Any]:
    """Ждёт terminal state bounded timeout, не удерживая index lock."""
    if timeout_seconds < 0 or timeout_seconds > 300:
        return {"error": "timeout_seconds должен быть в диапазоне 0..300"}
    job = _index_manager.wait(job_id, timeout_seconds)
    if job is None:
        return {"error": "Индексирующая job не найдена", "job_id": job_id}
    return job


@mcp.tool(name="booster.task_complete")
def task_complete(
    task_id: str | None = None,
    repo_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Queues a final bounded reindex and immutable snapshot for an agent task."""
    active_repos = _sync_registered_repos()
    requested = (
        active_repos
        if repo_paths is None
        else [RepositoryRegistry.normalize(repo) for repo in repo_paths]
    )
    unknown = [repo for repo in requested if repo not in active_repos]
    if unknown:
        return {
            "error": "Репозитории не зарегистрированы в Booster",
            "unknown_repos": unknown,
            "repos": active_repos,
        }

    for repo in requested:
        _start_index_repo_job(repo, reason="task_complete", task_id=task_id)

    return {
        "accepted": True,
        "task_id": task_id,
        "repos": requested,
        "indexing": {
            repo: _index_jobs_snapshot().get(repo, {})
            for repo in requested
        },
        "snapshot_policy": "immutable commit-bound history; previous snapshots are preserved",
    }


@mcp.tool()
def list_repos() -> dict[str, Any]:
    """Возвращает список всех репозиториев под управлением MCP."""
    repos = _sync_registered_repos()
    stats = indexer.stats() if hasattr(indexer, "stats") else {
        "files_indexed": len(indexer.symbols),
        "vectors_in_faiss": indexer.vector.index.ntotal,
    }
    return {
        "repos": repos,
        "total_files": stats["files_indexed"],
        "total_vectors": stats["vectors_in_faiss"],
        "indexing": _index_jobs_snapshot(),
        "registry": _registry_records_for_repos(repos),
        "generation_id": indexer.index_health().get("generation_id"),
        "stale": bool(indexer.index_health().get("stale", False)),
        "completeness": indexer.index_health().get("map_coverage", {}),
    }


@mcp.tool()
def get_repo_map(repo_path: str | None = None) -> dict[str, Any]:
    """
    Генерирует сжатую карту репозитория в стиле Aider RepoMap.
    Показывает структуру проекта, функции и классы (~4K токенов на 100K+ строк).

    Args:
        repo_path: Путь к репозиторию (если None, используется первый добавленный)

    Returns:
        Строка с картой репозитория
    """
    _sync_registered_repos()
    if not indexer.repos:
        return {"error": "Нет добавленных репозиториев. Используйте add_repo()"}

    if repo_path is None:
        r_path = indexer.repos[0]
    else:
        r_path = str(Path(repo_path).expanduser().resolve())

    if r_path not in indexer.repos:
        return {"error": f"Репозиторий не найден: {r_path}"}

    artifacts_dir = Path(r_path) / ".agents" / "booster"
    map_output = artifacts_dir / "repo_map_architecture.md"
    if not map_output.exists():
        map_output = artifacts_dir / "repo_map.md"
    if map_output.exists():
        with open(map_output, "r", encoding="utf-8") as f:
            return {"repo_map": f.read()}

    active_job = _index_manager.get(repo=r_path)
    if active_job and active_job.get("status") in {"queued", "running", "cancelling"}:
        return {
            "ready": False,
            "indexing": active_job,
            "warning": "Repo Map ещё строится; возвращён последний готовый snapshot отсутствует",
        }

    # Fallback to generating if it doesn't exist
    if r_path not in repo_maps:
        repo_maps[r_path] = RepoMap(root=r_path)

    repo_map = repo_maps[r_path]
    map_content = str(cast(Any, repo_map).get_architecture_map())

    if not map_content:
        return {
            "warning": (
                "Не удалось сгенерировать карту репозитория (пустой или нет поддерживаемых языков)"
            )
        }

    map_output.parent.mkdir(parents=True, exist_ok=True)
    map_output.write_text(map_content, encoding="utf-8")
    if map_output.name != "repo_map.md":
        (map_output.parent / "repo_map.md").write_text(map_content, encoding="utf-8")

    return {"repo_map": map_content}


@mcp.tool()
def get_code_city(
    repo_path: str | None = None,
    output_file: str = "code_city.html",
) -> dict[str, Any]:
    """
    Генерирует 3D визуализацию проекта в виде "города".

    Здания = файлы, высота = метрики (строки, функции, сложность),
    цвет = язык/тип, связи = импорты/вызовы.

    Args:
        repo_path: Путь к репозиторию (если None, используется первый добавленный)
        output_file: Имя выходного HTML файла

    Returns:
        Путь к HTML файлу и статистика
    """
    _sync_registered_repos()
    if not indexer.repos:
        return {"error": "Нет добавленных репозиториев. Используйте add_repo()"}

    if repo_path is None:
        r_path = indexer.repos[0]
    else:
        r_path = str(Path(repo_path).expanduser().resolve())

    if r_path not in indexer.repos:
        return {"error": f"Репозиторий не найден: {r_path}"}

    html_path = Path(r_path) / ".agents" / "booster" / "code_city.html"

    if html_path.exists():
        return {
            "success": True,
            "html_path": str(html_path),
            "message": f"Открой {str(html_path)} в браузере для просмотра 3D города",
            "stats": "Из кэша",
        }

    # Fallback to generating if it doesn't exist
    viz = CodeCityVisualizer(indexer)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    result = cast(dict[str, Any], viz.generate_visualization(r_path, str(html_path)))

    if result.get("error"):
        return result

    metrics = cast(dict[str, Any], result.get("metrics", {}))

    return {
        "success": True,
        "html_path": str(html_path),
        "message": f"Открой {result['html_path']} в браузере для просмотра 3D города",
        "stats": {
            "files": result["buildings"],
            "connections": result["connections"],
            "districts": result["districts"],
            "total_lines": metrics["lines"],
            "total_functions": metrics["functions"],
            "total_classes": metrics["classes"],
            "total_complexity": metrics["complexity"],
            "total_size_kb": round(metrics["bytes"] / 1024, 1),
        },
    }


def main():
    """Точка входа для запуска MCP сервера как пакета или скрипта."""
    _initialize_runtime()
    _start_city_web()
    mcp.run()


if __name__ == "__main__":
    main()
