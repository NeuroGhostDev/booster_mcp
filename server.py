import os
import threading
from pathlib import Path
from typing import Optional
from fastmcp import FastMCP
from indexer import RepoIndexer
from watcher import start_watch
from repomap import RepoMap
from flipchart import Flipchart
from skill_installer import auto_install_bundled_skills, install_bundled_skills, list_bundled_skills
from toolkit import CodeToolkit
from visualizer import CodeCityVisualizer
import city_server

# Начальные репозитории из env (может быть пустым)
initial_repos = [r.strip()
                 for r in os.getenv("REPOS", "").split(",") if r.strip()]
if not initial_repos:
    initial_repos = []

# Callback для генерации Code City после индексации


def on_index_callback(repo_path: str):
    """Генерирует Code City после индексации репозитория."""
    try:
        viz = CodeCityVisualizer(indexer)
        city_output = str(Path(repo_path) / "code_city.html")
        viz.generate_visualization(repo_path, city_output)
    except Exception as e:
        print(f"⚠️  Не удалось сгенерировать Code City для {repo_path}: {e}")


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

# Инициализация flipchart
flipchart = Flipchart(indexer)

# Инициализация toolkit
toolkit = CodeToolkit(indexer, indexer.repos)

# Инициализация visualizer
visualizer = CodeCityVisualizer(indexer)


@mcp.tool()
def semantic_search(query: str):
    """Ищет фрагменты кода по смыслу (векторный поиск)."""
    return indexer.search(query)


@mcp.tool()
def find_symbol(name: str):
    """Ищет функцию или класс по имени."""
    return {
        "success": True,
        "html_path": str(Path(output_file).resolve()),
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
    repo_path = Path(repo_path).expanduser().resolve()
    if not repo_path.exists():
        return {"error": f"Путь не существует: {repo_path}"}
    if not repo_path.is_dir():
        return {"error": f"Это не директория: {repo_path}"}

    repo_str = str(repo_path)
    if repo_str in indexer.repos:
        return {"warning": f"Репозиторий уже добавлен: {repo_str}", "repos": indexer.repos}

    indexer.repos.append(repo_str)
    indexer.full_index()

    # Запуск watchdog при первом добавлении репозитория
    if len(indexer.repos) == 1:
        start_watch(indexer, indexer.repos)

    result = {
        "success": f"Добавлен репозиторий: {repo_str}",
        "repos": indexer.repos,
        "files_indexed": len(indexer.symbols),
        "code_city": f"{repo_str}\\code_city.html",
    }

    return result


@mcp.tool()
def remove_repo(repo_path: str):
    """Удаляет репозиторий из списка индексации (данные сохраняются в индексе)."""
    repo_path = Path(repo_path).expanduser().resolve()
    repo_str = str(repo_path)

    if repo_str not in indexer.repos:
        return {"error": f"Репозиторий не найден в списке: {repo_str}", "repos": indexer.repos}

    indexer.repos.remove(repo_str)
    return {"success": f"Удалён репозиторий: {repo_str}", "repos": indexer.repos}


@mcp.tool()
def reindex_repo(repo_path: str):
    """Переиндексирует указанный репозиторий (полная очистка и новая индексация)."""
    repo_path = Path(repo_path).expanduser().resolve()
    repo_str = str(repo_path)

    if repo_str not in indexer.repos:
        return {"error": f"Репозиторий не в списке индексации: {repo_str}"}

    # Очистка данных для файлов этого репозитория
    files_to_remove = [f for f in indexer.symbols.keys() if Path(
        f).resolve().parts[:len(repo_path.parts)] == repo_path.parts]
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

    return {
        "success": f"Переиндексирован: {repo_str}",
        "files_in_repo": len([f for f in indexer.symbols if Path(f).resolve().is_relative_to(repo_path)]),
        "code_city": f"{repo_str}\\code_city.html",
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
def get_repo_map(repo_path: str = None):
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
        repo_path = indexer.repos[0]

    repo_path = Path(repo_path).expanduser().resolve()
    repo_str = str(repo_path)

    if repo_str not in indexer.repos:
        return {"error": f"Репозиторий не найден: {repo_str}"}

    # Создаём или берём из кэша RepoMap
    if repo_str not in repo_maps:
        repo_maps[repo_str] = RepoMap(root=repo_str)

    repo_map = repo_maps[repo_str]
    map_content = repo_map.get_repo_map()

    if not map_content:
        return {"warning": "Не удалось сгенерировать карту репозитория (пустой или нет поддерживаемых языков)"}

    return {"repo_map": map_content}


# === Flipchart инструменты для дебага ===

@mcp.tool()
def flipchart_quick_debug(symbol: str, max_depth: int = 3):
    """
    Быстрый дебаг символа: генерирует Mermaid call graph + семантический контекст.
    Идеально для анализа сложных систем.
    """
    return flipchart.quick_debug(symbol, max_depth)


@mcp.tool()
def flipchart_create_session(session_id: str, symbols: list[str]):
    """
    Создаёт сессию дебага для отслеживания группы символов.
    Автоматически генерирует начальные диаграммы.
    """
    return flipchart.create_session(session_id, symbols)


@mcp.tool()
def flipchart_add_note(session_id: str, label: str, content: str,
                       symbols: Optional[list[str]] = None):
    """
    Добавляет заметку-инсайт на флипчарт сессии.
    Можно привязать к конкретным символам.
    """
    return flipchart.add_note(session_id, label, content, symbols)


@mcp.tool()
def flipchart_get_board(session_id: str):
    """
    Возвращает полный флипчарт сессии: все диаграммы и заметки.
    """
    return flipchart.get_board(session_id)


@mcp.tool()
def flipchart_call_graph(symbol: str, max_depth: int = 5):
    """
    Генерирует Mermaid-диаграмму вызовов для символа.
    """
    return {"mermaid": flipchart.generate_call_graph_mermaid(symbol, max_depth)}


@mcp.tool()
def flipchart_sequence_diagram(symbol: str, depth: int = 5):
    """
    Генерирует Sequence-диаграмму выполнения от символа.
    """
    return {"mermaid": flipchart.generate_sequence_diagram(symbol, depth)}


# === Toolkit инструменты ===

@mcp.tool()
def code_grep(pattern: str, file_pattern: str = "*",
              ignore_case: bool = True, max_results: int = 100):
    """Регулярный поиск по всем файлам проектов"""
    return toolkit.code_grep(pattern, file_pattern, ignore_case, max_results)


@mcp.tool()
def read_with_context(file: str, line: int, context: int = 20):
    """Читает файл с ±N строк вокруг указанной линии"""
    return toolkit.read_with_context(file, line, context)


@mcp.tool()
def read_file(file: str, start: int = 0, end: int = 100):
    """Читает диапазон строк из файла (0-indexed)"""
    return toolkit.read_file(file, start, end)


@mcp.tool()
def git_diff(path: str, commit: str = "HEAD", staged: bool = False):
    """Показывает изменения в файле/репозитории"""
    return toolkit.git_diff(path, commit, staged)


@mcp.tool()
def git_log(path: str, limit: int = 10):
    """История коммитов для файла/репозитория"""
    return toolkit.git_log(path, limit)


@mcp.tool()
def run_command(cmd: str, cwd: str = None, timeout: int = 30000):
    """Выполняет команду в shell. timeout в миллисекундах"""
    return toolkit.run_command(cmd, cwd, timeout)


@mcp.tool()
def analyze_error(error_text: str, symbols: Optional[list[str]] = None):
    """Ищет в коде потенциальные причины ошибки по тексту stacktrace"""
    return toolkit.analyze_error(error_text, symbols)


@mcp.tool()
def list_configs(repo: str = None):
    """Находит все конфигурационные файлы в репозитории"""
    return toolkit.list_configs(repo)


@mcp.tool()
def project_memory(action: str, key: str, value: str = None, repo: str = None):
    """
    Управление долгосрочной памятью проекта.
    action: get, set, delete, list, clear
    """
    return toolkit.project_memory(action, key, value, repo)


@mcp.tool()
def compare_symbols(symbol: str, file1: str, file2: str):
    """Сравнивает реализацию символа в двух файлах через diff"""
    return toolkit.compare_symbols(symbol, file1, file2)


@mcp.tool()
def find_duplicates(min_lines: int = 5, max_results: int = 50):
    """Ищет дублирующиеся блоки кода (copy-paste)"""
    return toolkit.find_duplicates(min_lines, max_results)


@mcp.tool()
def external_deps(symbol: str = None, file: str = None):
    """Находит внешние зависимости: HTTP, БД, Redis, Kafka, файлы, subprocess"""
    return toolkit.external_deps(symbol, file)


@mcp.tool()
def get_code_city(repo_path: str = None, output_file: str = 'code_city.html'):
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
        repo_path = indexer.repos[0]

    repo_path = Path(repo_path).expanduser().resolve()
    repo_str = str(repo_path)

    if repo_str not in indexer.repos:
        return {"error": f"Репозиторий не найден: {repo_str}"}

    # Переинициализируем визуализатор с актуальным indexer
    viz = CodeCityVisualizer(indexer)
    result = viz.generate_visualization(repo_str, output_file)

    if isinstance(result, dict) and result.get('error'):
        return result

    return {
        "success": True,
        "html_path": str(Path(output_file).resolve()),
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


if __name__ == "__main__":
    mcp.run()
