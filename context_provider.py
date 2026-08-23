import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repomap import RepoMap
from repository_lifecycle import RepositorySnapshotStore


def get_repo_artifacts_status(repo_path: str | Path) -> dict[str, object]:
    """Возвращает метаданные канонических артефактов Booster для репозитория."""
    repo = Path(repo_path).expanduser().resolve()
    artifacts_dir = repo / ".agents" / "booster"

    def get_file_status(path: Path) -> dict[str, str | int | bool]:
        if not path.is_file():
            return {"path": str(path), "exists": False}

        stat = path.stat()
        return {
            "path": str(path),
            "exists": True,
            "size_bytes": stat.st_size,
            "modified_at_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }

    snapshot_store = RepositorySnapshotStore(repo)
    health_path = artifacts_dir / "index_health.json"
    try:
        index_health = json.loads(health_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        index_health = {}
    if not isinstance(index_health, dict):
        index_health = {}
    return {
        "repo": str(repo),
        "artifacts_dir": str(artifacts_dir),
        "artifacts": {
            "repo_map": get_file_status(artifacts_dir / "repo_map.md"),
            "code_city": get_file_status(artifacts_dir / "code_city.html"),
            "scan_config": get_file_status(artifacts_dir / "scan_config.json"),
            "scan_report": get_file_status(artifacts_dir / "scan_report.json"),
        },
        "split_artifacts": {
            "repo_map_architecture": get_file_status(artifacts_dir / "repo_map_architecture.md"),
            "repo_map_symbols": get_file_status(artifacts_dir / "repo_map_symbols.md"),
            "index_health": get_file_status(artifacts_dir / "index_health.json"),
        },
        "index_health": index_health,
        "generation_id": index_health.get("generation_id"),
        "stale": bool(index_health.get("stale", False)),
        "completeness": index_health.get("map_coverage", {}),
        "snapshot_history": {
            "latest": snapshot_store.latest(),
            "items": snapshot_store.list_snapshots(limit=20),
        },
    }


def setup_context_provider(mcp: Any, indexer: Any, repo_maps: dict[str, RepoMap]) -> None:
    """
    Регистрирует ресурсы (resources) и инструменты (tools) для Context Injection.
    """

    @mcp.resource("repo://map")
    def get_repo_map_resource() -> str:
        """Возвращает карту репозитория (структуру)."""
        if not indexer.repos:
            return "Нет добавленных репозиториев"

        repo = indexer.repos[0]
        architecture_map = Path(repo) / ".agents" / "booster" / "repo_map_architecture.md"
        if architecture_map.is_file():
            return architecture_map.read_text(encoding="utf-8")
        index_health = getattr(indexer, "index_health", None)
        if callable(index_health) and not index_health().get("ready", False):
            return "Индексация ещё не завершена; Repo Map пока недоступна."
        repo_map = repo_maps.get(repo)
        if repo_map is None:
            repo_map = RepoMap(root=repo)
            repo_maps[repo] = repo_map

        return repo_map.get_repo_map() or "Карта пуста"

    @mcp.resource("repo://artifacts")
    def get_repo_artifacts_resource() -> str:
        """Возвращает статус карт, визуализации и bounded scan-артефактов."""
        if not indexer.repos:
            return "Нет добавленных репозиториев"

        return json.dumps(
            get_repo_artifacts_status(indexer.repos[0]),
            ensure_ascii=False,
            indent=2,
        )

    @mcp.resource("repo://stack")
    def get_repo_stack_resource() -> str:
        """Возвращает обзор используемых технологий в проекте (на основе анализа файлов)."""
        if not indexer.repos:
            return "Нет добавленных репозиториев"

        exts = set()
        symbols_snapshot = getattr(indexer, "symbols_snapshot", None)
        symbols = symbols_snapshot() if callable(symbols_snapshot) else indexer.symbols
        for f in symbols.keys():
            ext = Path(f).suffix.lower()
            if ext:
                exts.add(ext)
        return f"Используемые типы файлов в проекте (стек): {', '.join(sorted(exts))}"

    @mcp.resource("repo://conventions")
    def get_repo_conventions_resource() -> str:
        """Возвращает код-стайл и конвенции из конфигурационных файлов репозитория."""
        if not indexer.repos:
            return "Нет добавленных репозиториев"

        repo_path = Path(indexer.repos[0])
        conventions = []

        config_names = (
            ".editorconfig",
            "pyproject.toml",
            "package.json",
            ".eslintrc",
            ".prettierrc",
            "tox.ini",
            ".gitignore",
        )
        for config_name in config_names:
            config_path = repo_path / config_name
            if config_path.exists():
                try:
                    content = config_path.read_text(encoding="utf-8")
                    # Обрезаем если слишком длинный
                    if len(content) > 1500:
                        content = content[:1500] + "\n... (оборвано)"
                    conventions.append(f"=== {config_name} ===\n{content}\n")
                except Exception:
                    pass

        if not conventions:
            return "Специфичные файлы с конвенциями не найдены."
        return "\n".join(conventions)

    @mcp.tool()
    def get_repo_artifacts(repo_path: str | None = None) -> dict[str, object]:
        """Возвращает статус карт, визуализации и bounded scan-артефактов."""
        if not indexer.repos:
            return {"error": "Нет добавленных репозиториев. Используйте add_repo()."}

        if repo_path is None:
            repo = indexer.repos[0]
        else:
            repo = str(Path(repo_path).expanduser().resolve())

        if repo not in indexer.repos:
            return {"error": f"Репозиторий не найден: {repo}"}

        return get_repo_artifacts_status(repo)

    @mcp.tool()
    def inject_context(
        include_map: bool = True,
        include_stack: bool = True,
        include_conventions: bool = False,
    ):
        """
        Собирает полный контекст по проекту (repo map, стек и конвенции),
        чтобы загрузить его в память агента в начале работы.
        """
        context = []
        if include_map:
            context.append("=== Карта репозитория (repo://map) ===\n" + get_repo_map_resource())
        if include_stack:
            context.append("=== Стек технологий (repo://stack) ===\n" + get_repo_stack_resource())
        if include_conventions:
            context.append(
                "=== Конвенции проекта (repo://conventions) ===\n" + get_repo_conventions_resource()
            )

        return {"context": "\n\n".join(context)}
