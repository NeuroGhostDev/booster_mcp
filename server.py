import os
import threading
from pathlib import Path
from typing import Optional
from fastmcp import FastMCP
from indexer import RepoIndexer
from watcher import start_watch
from repomap import RepoMap
from flipchart import setup_flipchart_tools
from skill_installer import auto_install_bundled_skills, install_bundled_skills, list_bundled_skills
from toolkit import setup_toolkit_tools
from visualizer import CodeCityVisualizer
from context_provider import setup_context_provider
from context7_bridge import setup_context7_bridge
import city_server

# Начальные репозитории из env (может быть пустым)
initial_repos = [r.strip()
                 for r in os.getenv("REPOS", "").split(",") if r.strip()]
if not initial_repos:
    initial_repos = []

# Callback для генерации Code City после индексации


def on_index_callback(repo_path: str):
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
        map_content = rm.get_repo_map()
        if map_content:
            map_output = base_dir / "repo_map.md"
            with open(map_output, "w", encoding="utf-8") as f:
                f.write(map_content)
                
    except Exception as e:
        print(f"⚠️  Ошибка автогенерации артефактов для {repo_path}: {e}")

# Инициализация без автоматической индексации (агент сам добавит репозитории)
indexer = RepoIndexer(initial_repos, on_index_complete=on_index_callback)
repo_maps = {}  # Кэш RepoMap для каждого репозитория

# Автоустановка встроенных скилов для агента.
auto_install_bundled_skills()

if initial_repos:
    indexer.full_index()
    start_watch(indexer, indexer.repos)
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

# Инициализация visualizer
visualizer = CodeCityVisualizer(indexer)


@mcp.tool()
def semantic_search(query: str):
    """Ищет фрагменты кода по смыслу (векторный поиск)."""
    return indexer.search(query)


@mcp.tool()
def find_symbol(name: str):
    """Ищет функцию или класс по имени."""
    matches = []
    for filepath, file_symbols in indexer.symbols.items():
        for sym in file_symbols:
            if sym.get("name") == name:
                matches.append(sym)
    
    if not matches:
        return {"error": f"Символ '{name}' не найден"}
    
    return {"symbols": matches}




@mcp.tool()
def repo_stats():
    """Возвращает статистику проиндексированного репозитория."""
    return {
        "repos": indexer.repos,
        "files_indexed": len(indexer.symbols),
        "vectors_in_faiss": indexer.vector.index.ntotal
    }


@mcp.tool()
def list_agent_skills():
    """Возвращает список встроенных agent skills, поставляемых вместе с MCP."""
    return {
        "bundled_skills": list_bundled_skills(),
        "target_dir": str(Path.home() / ".agents" / "skills"),
    }


@mcp.tool()
def install_agent_skills(overwrite: bool = True):
    """Синхронизирует встроенные agent skills в ~/.agents/skills."""
    return install_bundled_skills(overwrite=overwrite)


@mcp.tool()
def add_repo(repo_path: str):
    """Добавляет репозиторий для индексации и индексирует его."""
    r_path = Path(repo_path).expanduser().resolve()
    if not r_path.exists() or not r_path.is_dir():
        return {"error": f"Путь {repo_path} не существует или не является директорией"}

    repo_str = str(r_path)
    if repo_str in indexer.repos:
        return {"warning": f"Репозиторий уже добавлен: {repo_str}", "repos": indexer.repos}

    indexer.repos.append(repo_str)
    indexer.full_index()

    # Запуск watchdog при первом добавлении репозитория
    if len(indexer.repos) == 1:
        start_watch(indexer, indexer.repos)

    base_dir = r_path / ".agents" / "booster"
    result = {
        "success": f"Добавлен репозиторий: {repo_str}",
        "repos": indexer.repos,
        "files_indexed": len(indexer.symbols),
        "code_city": str(base_dir / "code_city.html"),
        "repo_map": str(base_dir / "repo_map.md"),
    }

    return result


@mcp.tool()
def remove_repo(repo_path: str):
    """Удаляет репозиторий из списка индексации (данные сохраняются в индексе)."""
    r_path = Path(repo_path).expanduser().resolve()
    repo_str = str(r_path)

    if repo_str not in indexer.repos:
        return {"error": f"Репозиторий не найден в списке: {repo_str}", "repos": indexer.repos}

    indexer.repos.remove(repo_str)
    return {"success": f"Удалён репозиторий: {repo_str}", "repos": indexer.repos}


@mcp.tool()
def reindex_repo(repo_path: str):
    """Переиндексирует указанный репозиторий (полная очистка и новая индексация)."""
    r_path = Path(repo_path).expanduser().resolve()
    repo_str = str(r_path)

    if repo_str not in indexer.repos:
        return {"error": f"Репозиторий не в списке индексации: {repo_str}"}

    # Очистка данных для файлов этого репозитория
    files_to_remove = [f for f in indexer.symbols.keys() if Path(f).resolve().is_relative_to(r_path)]
    for file in files_to_remove:
        indexer.vector.remove_file(file)
        indexer.graphs.clear_file(file)
        del indexer.symbols[file]

    # Переиндексация
    from indexer import IGNORED_DIRS
    for file in Path(repo_path).rglob("*"):
        if not file.is_file():
            continue
        if any(part in IGNORED_DIRS for part in file.parts):
            continue
        indexer.index_file(file)

    on_index_callback(repo_str)

    base_dir = r_path / ".agents" / "booster"
    return {
        "success": f"Переиндексирован: {repo_str}",
        "files_in_repo": len([f for f in indexer.symbols if Path(f).resolve().is_relative_to(repo_path)]),
        "code_city": str(base_dir / "code_city.html"),
        "repo_map": str(base_dir / "repo_map.md"),
    }


@mcp.tool()
def list_repos():
    """Возвращает список всех репозиториев под управлением MCP."""
    return {
        "repos": indexer.repos,
        "total_files": len(indexer.symbols),
        "total_vectors": indexer.vector.index.ntotal
    }


@mcp.tool()
def get_repo_map(repo_path: str | None = None):
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
    map_content = repo_map.get_repo_map()

    if not map_content:
        return {"warning": "Не удалось сгенерировать карту репозитория (пустой или нет поддерживаемых языков)"}

    map_output.parent.mkdir(parents=True, exist_ok=True)
    with open(map_output, "w", encoding="utf-8") as f:
        f.write(map_content)

    return {"repo_map": map_content}




@mcp.tool()
def get_code_city(repo_path: str | None = None, output_file: str = "code_city.html"):
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
    result = viz.generate_visualization(r_path, str(html_path))

    if isinstance(result, dict) and result.get('error'):
        return result

    return {
        "success": True,
        "html_path": str(html_path),
        "message": f"Открой {result['html_path']} в браузере для просмотра 3D города",
        "stats": {
            "files": result['buildings'],
            "connections": result['connections'],
            "districts": result['districts'],
            "total_lines": result['metrics']['lines'],
            "total_functions": result['metrics']['functions'],
            "total_classes": result['metrics']['classes'],
            "total_complexity": result['metrics']['complexity'],
            "total_size_kb": round(result['metrics']['bytes'] / 1024, 1),
        }
    }


def main():
    """Точка входа для запуска MCP сервера как пакета или скрипта."""
    mcp.run()


if __name__ == "__main__":
    main()
