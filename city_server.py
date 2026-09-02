"""
Code City Web UI — Веб-интерфейс для управления MCP Code Intelligence.
Управление репозиториями, визуализация Code City, статистика.
"""

# ruff: noqa: E501
import json
import logging
import os
import sys
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, quote, urlparse

# Импортируем компоненты MCP
from indexer import RepoIndexer
from repomap import RepoMap
from visualizer import CodeCityVisualizer
from watcher import start_watch

# Keep the historical module-level name patchable for integrations/tests while
# using the threaded implementation for actual requests.
HTTPServer = ThreadingHTTPServer

# Глобальные переменные
indexer: RepoIndexer | None = None
watch_started = False
watch_handle: tuple[Any, Any] | None = None
repo_maps: dict[str, RepoMap] = {}
logger = logging.getLogger(__name__)


def _code_city_path(repo: str | Path) -> Path:
    return Path(repo).expanduser().resolve() / ".agents" / "booster" / "code_city.html"


def _registered_repo_path(repos: list[str], requested: str | None) -> Path | None:
    """Resolve a request only through an already registered repository value."""
    selected: str | None
    if requested is None:
        selected = repos[0] if repos else None
    else:
        selected = None
        for registered in repos:
            if requested == registered:
                selected = registered
                break
    if selected is None:
        return None
    return Path(selected).expanduser().resolve()


def set_indexer(idx: RepoIndexer) -> None:
    """Устанавливает внешний indexer (при запуске из server.py для общего состояния)."""
    global indexer, watch_started, watch_handle
    indexer = idx
    watch_started = False
    watch_handle = None


def ensure_watch_started(idx: RepoIndexer | None = None) -> None:
    """Starts one shared watcher and schedules repositories added later."""
    global indexer, watch_started, watch_handle
    current = idx or get_indexer()
    if not current.repos:
        return
    if watch_handle is None:
        watch_handle = start_watch(current, current.repos)
    else:
        observer, watcher = watch_handle
        for repo in current.repos:
            watcher.schedule_repository(observer, repo)
    watch_started = True


def stop_watch() -> None:
    """Stops the shared watcher for bounded build commands."""
    global watch_started, watch_handle
    if watch_handle is None:
        watch_started = False
        return
    observer, _watcher = watch_handle
    observer.stop()
    observer.join(timeout=5)
    watch_handle = None
    watch_started = False


def get_indexer() -> RepoIndexer:
    """Ленивая инициализация indexer (используется при самостоятельном запуске)."""
    global indexer
    if indexer is None:
        initial_repos = [r.strip() for r in os.getenv("REPOS", "").split(",") if r.strip()]
        indexer = RepoIndexer(initial_repos)
        if initial_repos:
            indexer.full_index()
            ensure_watch_started(indexer)
            for repo in initial_repos:
                repo_maps[repo] = RepoMap(root=repo)
    return indexer


class CodeCityHandler(SimpleHTTPRequestHandler):
    """HTTP обработчик с API для управления репозиториями."""

    def send_json_response(self, data: Any, status: int = 200) -> None:
        """Отправляет JSON ответ."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def send_html_response(self, content: str, status: int = 200) -> None:
        """Отправляет HTML ответ."""
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def do_OPTIONS(self) -> None:
        """CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        """Обработка GET запросов."""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # API endpoints
        if path == "/api/repos":
            self.handle_list_repos()
        elif path == "/api/stats":
            self.handle_stats()
        elif path == "/api/code_city":
            self.handle_get_code_city(query.get("repo", [None])[0])
        elif path == "/api/repo_map":
            self.handle_get_repo_map(query.get("repo", [None])[0])
        elif path == "/city":
            self.handle_serve_code_city(query.get("repo", [None])[0])
        elif path == "/":
            self.handle_index()
        else:
            # Статические файлы
            return super().do_GET()

    def do_POST(self) -> None:
        """Обработка POST запросов."""
        parsed = urlparse(self.path)
        path = parsed.path

        # Чтение тела запроса
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            loaded_body: Any = json.loads(body) if body else {}
        except json.JSONDecodeError:
            loaded_body = {}
        if isinstance(loaded_body, dict):
            raw_data = cast(dict[Any, Any], loaded_body)
            data = {str(key): value for key, value in raw_data.items()}
        else:
            data = {}

        # API endpoints
        if path == "/api/repos/add":
            self.handle_add_repo(data.get("path", ""))
        elif path == "/api/repos/remove":
            self.handle_remove_repo(data.get("path", ""))
        elif path == "/api/repos/reindex":
            self.handle_reindex_repo(data.get("path", ""))
        elif path == "/api/repos/generate_city":
            self.handle_generate_city(data.get("repo", ""))
        else:
            self.send_json_response({"error": "Not found"}, 404)

    def handle_index(self) -> None:
        """Главная страница с UI."""
        html = self.generate_main_ui()
        self.send_html_response(html)

    def handle_list_repos(self) -> None:
        """Список репозиториев."""
        idx = get_indexer()
        stats = idx.stats()
        result: dict[str, Any] = {
            "repos": list(idx.repos),
            "total_files": stats["files_indexed"],
            "total_vectors": stats["vectors_in_faiss"],
        }
        self.send_json_response(result)

    def handle_stats(self) -> None:
        """Статистика по репозиториям."""
        idx = get_indexer()
        symbols = idx.symbols_snapshot()
        index_stats = idx.stats()
        stats: dict[str, Any] = {
            "repos": [],
            "total_files": index_stats["files_indexed"],
            "total_vectors": index_stats["vectors_in_faiss"],
            "total_functions": sum(len(syms) for syms in symbols.values()),
        }

        # Группировка по репозиториям
        repo_files: dict[str, list[str]] = {}
        for file_path in symbols.keys():
            for repo in idx.repos:
                if Path(file_path).is_relative_to(Path(repo)):
                    if repo not in repo_files:
                        repo_files[repo] = []
                    repo_files[repo].append(file_path)
                    break

        for repo, files in repo_files.items():
            repo_stats: dict[str, Any] = {
                "path": repo,
                "files": len(files),
                "has_city": _code_city_path(repo).exists(),
            }
            stats["repos"].append(repo_stats)

        self.send_json_response(stats)

    def handle_get_code_city(self, repo_path: str | None = None) -> None:
        """Получить Code City для репозитория."""
        idx = get_indexer()
        if not idx.repos:
            self.send_json_response({"error": "Нет репозиториев"}, 400)
            return

        registered_repo = _registered_repo_path(idx.repos, repo_path)
        if registered_repo is None:
            self.send_json_response({"error": "Репозиторий не зарегистрирован"}, 404)
            return
        repo_key = str(registered_repo)
        city_file = _code_city_path(registered_repo)
        if city_file.exists():
            self.send_json_response(
                {
                    "exists": True,
                    "path": str(city_file),
                    "url": f'/city?repo={quote(repo_key, safe="")}',
                }
            )
        else:
            self.send_json_response({"exists": False, "message": "Code City ещё не сгенерирован"})

    def handle_serve_code_city(self, repo_path: str | None) -> None:
        """Serves one registered Code City artifact without accepting paths."""
        idx = get_indexer()
        if not repo_path:
            self.send_json_response({"error": "Репозиторий не указан"}, 400)
            return
        registered_repo = _registered_repo_path(idx.repos, repo_path)
        if registered_repo is None:
            self.send_json_response({"error": "Репозиторий не зарегистрирован"}, 404)
            return
        city_file = _code_city_path(registered_repo)
        if not city_file.is_file():
            self.send_json_response({"error": "Code City ещё не сгенерирован"}, 404)
            return
        try:
            self.send_html_response(city_file.read_text(encoding="utf-8"))
        except OSError as exc:
            self.send_json_response({"error": str(exc)}, 500)

    def handle_get_repo_map(self, repo_path: str | None = None) -> None:
        """Получить текстовую карту репозитория."""
        idx = get_indexer()
        if not idx.repos:
            self.send_json_response({"error": "Нет репозиториев"}, 400)
            return

        registered_repo = _registered_repo_path(idx.repos, repo_path)
        if registered_repo is None:
            self.send_json_response({"error": "Репозиторий не зарегистрирован"}, 404)
            return
        repo_key = str(registered_repo)

        if repo_key not in repo_maps:
            repo_maps[repo_key] = RepoMap(root=registered_repo)

        repo_map = repo_maps[repo_key]
        map_content = str(cast(Any, repo_map).get_repo_map())

        self.send_json_response({"repo": repo_key, "map": map_content})

    def handle_add_repo(self, repo_path: str) -> None:
        """Добавить репозиторий."""
        if not repo_path:
            self.send_json_response({"error": "Путь не указан"}, 400)
            return

        idx = get_indexer()
        repo_dir = Path(repo_path).expanduser().resolve()

        if not repo_dir.exists():
            self.send_json_response({"error": f"Путь не существует: {repo_dir}"}, 404)
            return

        if not repo_dir.is_dir():
            self.send_json_response({"error": f"Это не директория: {repo_dir}"}, 400)
            return

        repo_str = str(repo_dir)
        if repo_str in idx.repos:
            self.send_json_response(
                {"warning": f"Репозиторий уже добавлен: {repo_str}", "repos": idx.repos}
            )
            return

        with idx.operation_lock:
            idx.repos.append(repo_str)
        on_change = getattr(idx, "on_repository_change", None)
        if callable(on_change):
            on_change(repo_str)
            self.send_json_response(
                {
                    "accepted": True,
                    "repository": repo_str,
                    "indexing": True,
                    "repos": list(idx.repos),
                }
            )
            return
        idx.index_repo(repo_str)

        # Запуск watchdog при первом добавлении
        ensure_watch_started(idx)

        # Генерация Code City
        city_generated = False
        city_error: str | None = None
        try:
            viz = CodeCityVisualizer(idx)
            city_output = str(_code_city_path(repo_dir))
            viz.generate_visualization(repo_str, city_output)
            city_generated = True
        except Exception as exc:
            city_error = type(exc).__name__
            logger.exception("Code City generation failed for %s", repo_str)

        self.send_json_response(
            {
                "success": f"Добавлен репозиторий: {repo_str}",
                "repos": list(idx.repos),
                "files_indexed": idx.stats()["files_indexed"],
                "code_city_generated": city_generated,
                "code_city_error": city_error,
            }
        )

    def handle_remove_repo(self, repo_path: str) -> None:
        """Удалить репозиторий."""
        if not repo_path:
            self.send_json_response({"error": "Путь не указан"}, 400)
            return

        idx = get_indexer()
        repo_str = str(Path(repo_path).expanduser().resolve())

        if repo_str not in idx.repos:
            self.send_json_response({"error": f"Репозиторий не найден: {repo_str}"}, 404)
            return

        with idx.operation_lock:
            idx.repos.remove(repo_str)
        self.send_json_response(
            {"success": f"Удалён репозиторий: {repo_str}", "repos": list(idx.repos)}
        )

    def handle_reindex_repo(self, repo_path: str) -> None:
        """Переиндексировать репозиторий."""
        if not repo_path:
            self.send_json_response({"error": "Путь не указан"}, 400)
            return

        idx = get_indexer()
        repo_dir = Path(repo_path).expanduser().resolve()
        repo_str = str(repo_dir)

        if repo_str not in idx.repos:
            self.send_json_response({"error": f"Репозиторий не в списке: {repo_str}"}, 404)
            return

        on_change = getattr(idx, "on_repository_change", None)
        if callable(on_change):
            on_change(repo_str)
            self.send_json_response(
                {
                    "accepted": True,
                    "repository": repo_str,
                    "indexing": True,
                }
            )
            return

        # Legacy standalone Code City mode keeps the synchronous fallback.
        idx.remove_repo(repo_str)
        idx.index_repo(repo_str)

        # Генерация Code City
        city_generated = False
        city_error: str | None = None
        try:
            viz = CodeCityVisualizer(idx)
            city_output = str(_code_city_path(repo_dir))
            viz.generate_visualization(repo_str, city_output)
            city_generated = True
        except Exception as exc:
            city_error = type(exc).__name__
            logger.exception("Code City regeneration failed for %s", repo_str)

        self.send_json_response(
            {
                "success": f"Переиндексирован: {repo_str}",
                "files_in_repo": len(
                    [
                        f
                        for f in idx.symbols_snapshot()
                        if Path(f).resolve().is_relative_to(repo_dir)
                    ]
                ),
                "code_city_generated": city_generated,
                "code_city_error": city_error,
            }
        )

    def handle_generate_city(self, repo_path: str) -> None:
        """Сгенерировать Code City."""
        idx = get_indexer()
        if not idx.repos:
            self.send_json_response({"error": "Нет репозиториев"}, 400)
            return

        if not repo_path:
            repo_path = idx.repos[0]
        else:
            repo_path = str(Path(repo_path).expanduser().resolve())
            if repo_path not in idx.repos:
                self.send_json_response({"error": "Репозиторий не зарегистрирован"}, 404)
                return

        try:
            viz = CodeCityVisualizer(idx)
            city_output = str(_code_city_path(repo_path))
            result = cast(dict[str, Any], viz.generate_visualization(repo_path, city_output))

            self.send_json_response(
                {
                    "success": True,
                    "path": city_output,
                    "stats": {
                        "buildings": result.get("buildings", 0),
                        "connections": result.get("connections", 0),
                        "districts": result.get("districts", 0),
                    },
                }
            )
        except Exception as e:
            self.send_json_response({"error": str(e)}, 500)

    def generate_main_ui(self) -> str:
        """Генерирует главную страницу UI."""
        return """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🏙️ Code City MCP — Управление репозиториями</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #fff;
            min-height: 100vh;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 30px;
        }
        header h1 {
            font-size: 28px;
            background: linear-gradient(90deg, #4ECDC4, #3776AB);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .stats-bar {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: rgba(255,255,255,0.05);
            padding: 20px;
            border-radius: 12px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
        }
        .stat-card h3 {
            font-size: 14px;
            color: #aaa;
            margin-bottom: 10px;
        }
        .stat-card .value {
            font-size: 32px;
            font-weight: bold;
            color: #4ECDC4;
        }
        .panel {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
        }
        .panel h2 {
            font-size: 20px;
            margin-bottom: 20px;
            color: #4ECDC4;
        }
        .add-repo-form {
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
        }
        .add-repo-form input {
            flex: 1;
            padding: 12px 20px;
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.2);
            background: rgba(255,255,255,0.05);
            color: #fff;
            font-size: 14px;
        }
        .add-repo-form input::placeholder {
            color: #666;
        }
        .btn {
            padding: 12px 24px;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            transition: all 0.3s;
        }
        .btn-primary {
            background: linear-gradient(90deg, #4ECDC4, #3776AB);
            color: #fff;
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(78,205,196,0.4);
        }
        .btn-danger {
            background: linear-gradient(90deg, #FF6B6B, #ee5a5a);
            color: #fff;
        }
        .btn-secondary {
            background: rgba(255,255,255,0.1);
            color: #fff;
        }
        .btn-secondary:hover {
            background: rgba(255,255,255,0.2);
        }
        .repo-list {
            list-style: none;
        }
        .repo-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 15px;
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
            margin-bottom: 10px;
            border: 1px solid rgba(255,255,255,0.05);
        }
        .repo-item:hover {
            background: rgba(255,255,255,0.06);
        }
        .repo-info {
            flex: 1;
        }
        .repo-path {
            font-size: 14px;
            margin-bottom: 5px;
            word-break: break-all;
        }
        .repo-meta {
            font-size: 12px;
            color: #888;
        }
        .repo-actions {
            display: flex;
            gap: 10px;
        }
        .btn-sm {
            padding: 8px 16px;
            font-size: 12px;
        }
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: #4ECDC4;
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .alert {
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .alert-success {
            background: rgba(78,205,196,0.2);
            border: 1px solid #4ECDC4;
            color: #4ECDC4;
        }
        .alert-error {
            background: rgba(255,107,107,0.2);
            border: 1px solid #FF6B6B;
            color: #FF6B6B;
        }
        .city-badge {
            display: inline-block;
            padding: 4px 10px;
            background: rgba(78,205,196,0.2);
            border-radius: 12px;
            font-size: 11px;
            color: #4ECDC4;
            margin-left: 10px;
        }
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #666;
        }
        .empty-state h3 {
            font-size: 18px;
            margin-bottom: 10px;
            color: #888;
        }
        iframe {
            width: 100%;
            height: 600px;
            border: none;
            border-radius: 12px;
            background: #fff;
        }
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        .tab {
            padding: 10px 20px;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 8px 8px 0 0;
            cursor: pointer;
            transition: all 0.3s;
        }
        .tab:hover {
            background: rgba(255,255,255,0.1);
        }
        .tab.active {
            background: rgba(78,205,196,0.2);
            border-color: #4ECDC4;
            color: #4ECDC4;
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🏙️ Code City MCP</h1>
            <button class="btn btn-secondary" onclick="refreshStats()">🔄 Обновить</button>
        </header>

        <div id="alert-container"></div>

        <div class="stats-bar">
            <div class="stat-card">
                <h3>📦 Репозиториев</h3>
                <div class="value" id="stat-repos">0</div>
            </div>
            <div class="stat-card">
                <h3>📄 Файлов</h3>
                <div class="value" id="stat-files">0</div>
            </div>
            <div class="stat-card">
                <h3>🔍 Векторов</h3>
                <div class="value" id="stat-vectors">0</div>
            </div>
            <div class="stat-card">
                <h3>🎯 Функций</h3>
                <div class="value" id="stat-functions">0</div>
            </div>
        </div>

        <div class="panel">
            <h2>➕ Добавить репозиторий</h2>
            <div class="add-repo-form">
                <input type="text" id="repo-path-input"
                       placeholder="Путь к репозиторию (например, C:\\\\Users\\\\MyProject)"
                       onkeypress="if(event.key==='Enter') addRepo()">
                <button class="btn btn-primary" onclick="addRepo()">Добавить</button>
            </div>
        </div>

        <div class="panel">
            <h2>📁 Репозитории</h2>
            <div class="tabs">
                <div class="tab active" onclick="switchTab('list')">Список</div>
                <div class="tab" onclick="switchTab('city')">Code City</div>
            </div>

            <div id="tab-list" class="tab-content active">
                <ul class="repo-list" id="repo-list">
                    <li class="empty-state">
                        <h3>Нет репозиториев</h3>
                        <p>Добавьте первый репозиторий выше</p>
                    </li>
                </ul>
            </div>

            <div id="tab-city" class="tab-content">
                <select id="city-repo-select" onchange="loadCity()"
                        style="width: 100%; padding: 12px; margin-bottom: 15px;
                               background: rgba(255,255,255,0.05);
                               border: 1px solid rgba(255,255,255,0.2);
                               border-radius: 8px; color: #fff;">
                    <option value="">Выберите репозиторий</option>
                </select>
                <div id="city-container"></div>
            </div>
        </div>
    </div>

    <script>
        let repos = [];

        // Загрузка при старте
        document.addEventListener('DOMContentLoaded', () => {
            loadStats();
            loadRepos();
        });

        // Переключение табов
        function switchTab(tab) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

            document.querySelector(`.tab:nth-child(${tab === 'list' ? 1 : 2})`).classList.add('active');
            document.getElementById(`tab-${tab}`).classList.add('active');

            if (tab === 'city') {
                updateCitySelect();
            }
        }

        // Показ уведомления
        function showAlert(message, type = 'success') {
            const container = document.getElementById('alert-container');
            const alert = document.createElement('div');
            alert.className = `alert alert-${type}`;
            alert.textContent = message;
            container.innerHTML = '';
            container.appendChild(alert);

            setTimeout(() => alert.remove(), 5000);
        }

        // Загрузка статистики
        async function loadStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();

                document.getElementById('stat-repos').textContent = data.repos.length;
                document.getElementById('stat-files').textContent = data.total_files.toLocaleString();
                document.getElementById('stat-vectors').textContent = (data.total_vectors || 0).toLocaleString();
                document.getElementById('stat-functions').textContent = (data.total_functions || 0).toLocaleString();
            } catch (e) {
                console.error('Ошибка загрузки статистики:', e);
            }
        }

        // Загрузка репозиториев
        async function loadRepos() {
            try {
                const res = await fetch('/api/repos');
                const data = await res.json();
                repos = data.repos || [];
                renderRepoList(data);
            } catch (e) {
                console.error('Ошибка загрузки репозиториев:', e);
            }
        }

        // Отрисовка списка репозиториев
        function renderRepoList(data) {
            const list = document.getElementById('repo-list');

            if (!data.repos || data.repos.length === 0) {
                list.innerHTML = `
                    <li class="empty-state">
                        <h3>Нет репозиториев</h3>
                        <p>Добавьте первый репозиторий выше</p>
                    </li>
                `;
                return;
            }

            list.innerHTML = data.repos.map(repo => `
                <li class="repo-item">
                    <div class="repo-info">
                        <div class="repo-path">${repo}</div>
                        <div class="repo-meta">
                            Файлов: ${data.total_files} | Векторов: ${data.total_vectors || 0}
                            ${hasCityFile(repo) ? '<span class="city-badge">🏙️ Code City</span>' : ''}
                        </div>
                    </div>
                    <div class="repo-actions">
                        <button class="btn btn-secondary btn-sm" onclick="reindexRepo('${repo}')">
                            🔄 Переиндексировать
                        </button>
                        <button class="btn btn-secondary btn-sm" onclick="generateCity('${repo}')">
                            🏙️ Code City
                        </button>
                        <button class="btn btn-danger btn-sm" onclick="removeRepo('${repo}')">
                            🗑️ Удалить
                        </button>
                    </div>
                </li>
            `).join('');
        }

        // Проверка наличия Code City
        function hasCityFile(repo) {
            // Упрощённая проверка - можно улучшить через API
            return true;
        }

        // Добавление репозитория
        async function addRepo() {
            const input = document.getElementById('repo-path-input');
            const path = input.value.trim();

            if (!path) {
                showAlert('Введите путь к репозиторию', 'error');
                return;
            }

            try {
                const res = await fetch('/api/repos/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path })
                });
                const data = await res.json();

                if (data.error || data.warning) {
                    showAlert(data.error || data.warning, data.error ? 'error' : 'success');
                } else {
                    showAlert(`Репозиторий добавлен: ${path}`);
                    input.value = '';
                    loadStats();
                    loadRepos();
                }
            } catch (e) {
                showAlert('Ошибка при добавлении репозитория', 'error');
            }
        }

        // Удаление репозитория
        async function removeRepo(path) {
            if (!confirm(`Удалить репозиторий из списка?\\n${path}`)) return;

            try {
                const res = await fetch('/api/repos/remove', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path })
                });
                const data = await res.json();

                if (data.error) {
                    showAlert(data.error, 'error');
                } else {
                    showAlert(data.success);
                    loadStats();
                    loadRepos();
                }
            } catch (e) {
                showAlert('Ошибка при удалении репозитория', 'error');
            }
        }

        // Переиндексация
        async function reindexRepo(path) {
            try {
                const res = await fetch('/api/repos/reindex', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path })
                });
                const data = await res.json();

                if (data.error) {
                    showAlert(data.error, 'error');
                } else {
                    showAlert(`${data.success} (${data.files_in_repo} файлов)`);
                    if (data.code_city_generated) {
                        showAlert('Code City сгенерирован');
                    }
                    loadStats();
                    loadRepos();
                }
            } catch (e) {
                showAlert('Ошибка при переиндексации', 'error');
            }
        }

        // Генерация Code City
        async function generateCity(repo) {
            try {
                const res = await fetch('/api/repos/generate_city', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ repo })
                });
                const data = await res.json();

                if (data.error) {
                    showAlert(data.error, 'error');
                } else {
                    showAlert(`Code City сгенерирован: ${data.stats.buildings} зданий, ${data.stats.connections} связей`);
                    loadRepos();
                }
            } catch (e) {
                showAlert('Ошибка при генерации Code City', 'error');
            }
        }

        // Обновление статистики
        function refreshStats() {
            loadStats();
            loadRepos();
            showAlert('Статистика обновлена');
        }

        // Обновление селекта репозиториев
        function updateCitySelect() {
            const select = document.getElementById('city-repo-select');
            select.innerHTML = '<option value="">Выберите репозиторий</option>' +
                repos.map(repo => `<option value="${repo}">${repo}</option>`).join('');
        }

        // Загрузка Code City
        function loadCity() {
            const repo = document.getElementById('city-repo-select').value;
            const container = document.getElementById('city-container');

            if (!repo) {
                container.innerHTML = '';
                return;
            }

            // Проверяем существование файла через API
            fetch(`/api/code_city?repo=${encodeURIComponent(repo)}`)
                .then(res => res.json())
                .then(data => {
                    if (data.exists) {
                        const cityPath = data.url;
                        // Создаём iframe с локальным путём
                        container.innerHTML = `
                            <div style="text-align: center; margin-bottom: 15px;">
                                <a href="${cityPath}" target="_blank" class="btn btn-primary">
                                    🚀 Открыть в полном экране
                                </a>
                            </div>
                            <iframe src="${cityPath}"></iframe>
                        `;
                    } else {
                        container.innerHTML = `
                            <div class="empty-state">
                                <h3>Code City ещё не сгенерирован</h3>
                                <p>Нажмите "Code City" в списке репозиториев</p>
                                <button class="btn btn-primary" onclick="generateCity('${repo}')" style="margin-top: 15px;">
                                    🏙️ Сгенерировать
                                </button>
                            </div>
                        `;
                    }
                });
        }
    </script>
</body>
</html>
"""

    def log_message(self, format: str, *args: Any) -> None:
        """Подавляет логирование."""
        pass


def run_server(port: int = 8080, open_browser: bool = True, host: str = "127.0.0.1"):
    """Запускает веб-сервер Code City UI."""
    server_address = (host, port)
    # Перехватываем ошибку занятого порта, чтобы не крашить MCP
    try:
        httpd = HTTPServer(server_address, CodeCityHandler)
    except OSError as e:
        print(f"⚠️  Web UI: порт {port} занят — {e}", file=sys.stderr)
        return

    actual_port = httpd.server_address[1]
    url = f"http://localhost:{actual_port}"

    # Пишем в stderr, чтобы не мешать MCP-протоколу на stdout
    print(
        f"""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   🏙️  Code City MCP Web UI запущен!                      ║
║                                                           ║
║   URL: {url}
║                                                           ║
║   Функции:                                                ║
║   • Управление репозиториями                             ║
║   • Code City 3D визуализация                            ║
║   • Статистика индексации                                ║
║   • RepoMap                                              ║
║                                                           ║
║   Нажми Ctrl+C для остановки                             ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
    """,
        file=sys.stderr,
    )

    if open_browser:
        threading.Thread(target=lambda: (time.sleep(1), webbrowser.open(url))).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Сервер остановлен", file=sys.stderr)
        httpd.shutdown()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Code City MCP Web UI")
    parser.add_argument("--port", type=int, default=8080, help="Порт сервера")
    parser.add_argument(
        "--no-browser", action="store_true", help="Не открывать браузер автоматически"
    )
    args = parser.parse_args()

    run_server(port=args.port, open_browser=not args.no_browser)
