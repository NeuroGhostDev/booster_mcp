import os
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from fastmcp import FastMCP

import city_server
from cognitive_runtime import setup_cognitive_runtime_tools
from context7_bridge import setup_context7_bridge
from context_provider import setup_context_provider
from flipchart import setup_flipchart_tools
from indexer import RepoIndexer
from repomap import RepoMap
from repository_scanner import RepositoryScanner
from skill_installer import auto_install_bundled_skills, install_bundled_skills, list_bundled_skills
from toolkit import setup_toolkit_tools
from visualizer import CodeCityVisualizer
from watcher import start_watch

# Начальные репозитории из env (может быть пустым)
initial_repos = [r.strip()
                 for r in os.getenv("REPOS", "").split(",") if r.strip()]
if not initial_repos:
    initial_repos = []

# Callback для генерации Code City после индексации


def on_index_callback(repo_path: str) -> None:
    """Генерирует Code City и Repo Map после индексации репозитория."""
    try:
        base_dir = Path(repo_path) / ".agents" / "booster"
        base_dir.mkdir(parents=True, exist_ok=True)

        # 1. Code City
        viz = CodeCityVisualizer(indexer)
        city_output = str(base_dir / "code_city.html")
        viz.generate_visualization(repo_path, city_output)

        # 2. Repo Map
        rm = RepoMap(root=repo_path)
        map_content = str(cast(Any, rm).get_repo_map())
        if map_content:
            map_output = base_dir / "repo_map.md"
            with open(map_output, "w", encoding="utf-8") as f:
                f.write(map_content)

    except Exception as e:
        print(f"⚠️  Ошибка автогенерации артефактов для {repo_path}: {e}")


# Инициализация без автоматической индексации (агент сам добавит репозитории)
indexer = RepoIndexer(initial_repos, on_index_complete=on_index_callback)
repo_maps: dict[str, RepoMap] = {}  # Кэш RepoMap для каждого репозитория
_index_lock = threading.RLock()
_index_jobs: dict[str, dict[str, Any]] = {}
_watch_started = False

# Автоустановка встроенных скилов для агента.
auto_install_bundled_skills()

if initial_repos:
    indexer.full_index()
    start_watch(indexer, indexer.repos)
    _watch_started = True
    for repo in initial_repos:
        repo_maps[repo] = RepoMap(root=repo)

# Запуск веб-интерфейса в фоновом потоке-демоне
_web_port = int(os.getenv("CITY_PORT", "8080"))
city_server.set_indexer(indexer)
_web_thread = threading.Thread(
    target=city_server.run_server,
    kwargs={"port": _web_port, "open_browser": False},
    daemon=True,
    name="city-web-ui",
)
_web_thread.start()

mcp = FastMCP("Booster")

# Регистрация инструментов
setup_flipchart_tools(mcp, indexer)
setup_toolkit_tools(mcp, indexer, indexer.repos)
setup_context_provider(mcp, indexer, repo_maps)
setup_context7_bridge(mcp, indexer)
setup_cognitive_runtime_tools(mcp, indexer, indexer.repos)

# Инициализация visualizer
visualizer = CodeCityVisualizer(indexer)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_index_job(repo: str, **updates: Any) -> None:
    current = _index_jobs.get(repo, {})
    current.update(updates)
    current["updated_at_utc"] = _utc_now()
    _index_jobs[repo] = current


def _ensure_watch_started() -> None:
    global _watch_started
    if _watch_started or not indexer.repos:
        return
    start_watch(indexer, indexer.repos)
    _watch_started = True


def _index_repo_job(repo: str) -> None:
    try:
        _set_index_job(repo, status="running",
                       started_at_utc=_utc_now(), error=None)
        with _index_lock:
            scan_result = indexer.index_repo(repo)
            repo_maps[repo] = RepoMap(root=repo)
            _ensure_watch_started()
        _set_index_job(
            repo,
            status="completed",
            completed_at_utc=_utc_now(),
            files_indexed=len(scan_result.files),
            scan_report=str(scan_result.save_report()),
        )
    except Exception as exc:
        _set_index_job(
            repo,
            status="failed",
            completed_at_utc=_utc_now(),
            error=str(exc),
            traceback=traceback.format_exc(),
        )


def _start_index_repo_job(repo: str) -> None:
    job = _index_jobs.get(repo, {})
    if job.get("status") in {"queued", "running"}:
        return
    _set_index_job(repo, status="queued", queued_at_utc=_utc_now(), error=None)
    thread = threading.Thread(
        target=_index_repo_job,
        args=(repo,),
        daemon=True,
        name=f"booster-index-{Path(repo).name or 'repo'}",
    )
    thread.start()


@mcp.tool()
def semantic_search(query: str) -> list[dict[str, Any]]:
    """Ищет фрагменты кода по смыслу (векторный поиск)."""
    return indexer.search(query)


@mcp.tool()
def hybrid_search(query: str, k: int = 5) -> list[dict[str, Any]]:
    """Объединяет semantic-поиск и BM25 для точных символов, API и естественного языка."""
    return indexer.hybrid_search(query, k=k)


@mcp.tool()
def find_symbol(name: str) -> dict[str, Any]:
    """Ищет функцию или класс по имени."""
    matches: list[dict[str, Any]] = []
    for file_symbols in indexer.symbols.values():
        for sym in file_symbols:
            if sym.get("name") == name:
                matches.append(sym)

    if not matches:
        return {"error": f"Символ '{name}' не найден"}

    return {"symbols": matches}


@mcp.tool()
def repo_stats() -> dict[str, Any]:
    """Возвращает статистику проиндексированного репозитория."""
    return {
        "repos": indexer.repos,
        "files_indexed": len(indexer.symbols),
        "vectors_in_faiss": indexer.vector.index.ntotal,
        "indexing": _index_jobs,
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

    repo_str = str(r_path)
    if repo_str in indexer.repos:
        return {
            "warning": f"Репозиторий уже добавлен: {repo_str}",
            "repos": indexer.repos,
            "indexing": _index_jobs.get(repo_str, {"status": "unknown"}),
        }

    with _index_lock:
        if repo_str not in indexer.repos:
            indexer.repos.append(repo_str)

    # Создание/обновление .ignore файла для отсечения мусора (node_modules, venv и т.д.)
    ignore_path = r_path / ".ignore"
    default_ignores = {
        "node_modules", "venv", ".venv", "env", ".env",
        "__pycache__", ".idea", ".vscode", "dist", "build",
        "target", ".next", ".nuxt", "out", "coverage", ".git", ".tox"
    }

    existing_ignores: set[str] = set()
    if ignore_path.exists():
        try:
            with open(ignore_path, "r", encoding="utf-8") as f:
                existing_ignores = set(line.strip()
                                       for line in f if line.strip())
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

    if wait:
        _index_repo_job(repo_str)
    else:
        _start_index_repo_job(repo_str)

    base_dir = r_path / ".agents" / "booster"
    result: dict[str, Any] = {
        "success": f"Репозиторий добавлен: {repo_str}",
        "repos": indexer.repos,
        "files_indexed": len(indexer.symbols),
        "indexing": _index_jobs.get(repo_str, {"status": "unknown"}),
        "code_city": str(base_dir / "code_city.html"),
        "repo_map": str(base_dir / "repo_map.md"),
    }

    return result


@mcp.tool()
def remove_repo(repo_path: str) -> dict[str, Any]:
    """Удаляет репозиторий из списка индексации (данные сохраняются в индексе)."""
    r_path = Path(repo_path).expanduser().resolve()
    repo_str = str(r_path)

    if repo_str not in indexer.repos:
        return {"error": f"Репозиторий не найден в списке: {repo_str}", "repos": indexer.repos}

    indexer.repos.remove(repo_str)
    return {"success": f"Удалён репозиторий: {repo_str}", "repos": indexer.repos}


@mcp.tool()
def reindex_repo(repo_path: str) -> dict[str, Any]:
    """Переиндексирует указанный репозиторий (полная очистка и новая индексация)."""
    r_path = Path(repo_path).expanduser().resolve()
    repo_str = str(r_path)

    if repo_str not in indexer.repos:
        return {"error": f"Репозиторий не в списке индексации: {repo_str}"}

    # Очистка данных для файлов этого репозитория
    files_to_remove = [f for f in indexer.symbols.keys() if Path(
        f).resolve().is_relative_to(r_path)]
    for file in files_to_remove:
        indexer.vector.remove_file(file)
        indexer.graphs.clear_file(file)
        del indexer.symbols[file]

    # Переиндексация в пределах тех же budgets, что у CLI и первоначального индекса.
    scan_result = RepositoryScanner(r_path).scan()
    for file in scan_result.files:
        indexer.index_file(file)

    on_index_callback(repo_str)

    base_dir = r_path / ".agents" / "booster"
    files_in_repo = [
        file_path
        for file_path in indexer.symbols
        if Path(file_path).resolve().is_relative_to(repo_path)
    ]
    return {
        "success": f"Переиндексирован: {repo_str}",
        "files_in_repo": len(files_in_repo),
        "code_city": str(base_dir / "code_city.html"),
        "repo_map": str(base_dir / "repo_map.md"),
    }


@mcp.tool()
def list_repos() -> dict[str, Any]:
    """Возвращает список всех репозиториев под управлением MCP."""
    return {
        "repos": indexer.repos,
        "total_files": len(indexer.symbols),
        "total_vectors": indexer.vector.index.ntotal
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
    if not indexer.repos:
        return {"error": "Нет добавленных репозиториев. Используйте add_repo()"}

    if repo_path is None:
        r_path = indexer.repos[0]
    else:
        r_path = str(Path(repo_path).expanduser().resolve())

    if r_path not in indexer.repos:
        return {"error": f"Репозиторий не найден: {r_path}"}

    map_output = Path(r_path) / ".agents" / "booster" / "repo_map.md"
    if map_output.exists():
        with open(map_output, "r", encoding="utf-8") as f:
            return {"repo_map": f.read()}

    # Fallback to generating if it doesn't exist
    if r_path not in repo_maps:
        repo_maps[r_path] = RepoMap(root=r_path)

    repo_map = repo_maps[r_path]
    map_content = str(cast(Any, repo_map).get_repo_map())

    if not map_content:
        return {
            "warning": (
                "Не удалось сгенерировать карту репозитория "
                "(пустой или нет поддерживаемых языков)"
            )
        }

    map_output.parent.mkdir(parents=True, exist_ok=True)
    with open(map_output, "w", encoding="utf-8") as f:
        f.write(map_content)

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
            "stats": "Из кэша"
        }

    # Fallback to generating if it doesn't exist
    viz = CodeCityVisualizer(indexer)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    result = cast(dict[str, Any], viz.generate_visualization(
        r_path, str(html_path)))

    if result.get('error'):
        return result

    metrics = cast(dict[str, Any], result.get("metrics", {}))

    return {
        "success": True,
        "html_path": str(html_path),
        "message": f"Открой {result['html_path']} в браузере для просмотра 3D города",
        "stats": {
            "files": result['buildings'],
            "connections": result['connections'],
            "districts": result['districts'],
            "total_lines": metrics['lines'],
            "total_functions": metrics['functions'],
            "total_classes": metrics['classes'],
            "total_complexity": metrics['complexity'],
            "total_size_kb": round(metrics['bytes'] / 1024, 1),
        }
    }


def main():
    """Точка входа для запуска MCP сервера как пакета или скрипта."""
    mcp.run()


if __name__ == "__main__":
    main()
