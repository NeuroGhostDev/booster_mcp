import json
from pathlib import Path

def setup_context_provider(mcp, indexer, repo_maps):
    """
    Регистрирует ресурсы (resources) и инструменты (tools) для Context Injection.
    """
    
    @mcp.resource("repo://map")
    def get_repo_map_resource() -> str:
        """Возвращает карту репозитория (структуру)."""
        if not indexer.repos:
            return "Нет добавленных репозиториев"
        repo = indexer.repos[0]
        if repo in repo_maps:
            return repo_maps[repo].get_repo_map() or "Карта пуста"
        return "Карта не сгенерирована"

    @mcp.resource("repo://stack")
    def get_repo_stack_resource() -> str:
        """Возвращает обзор используемых технологий в проекте (на основе анализа файлов)."""
        if not indexer.repos:
            return "Нет добавленных репозиториев"
        
        exts = set()
        for f in indexer.symbols.keys():
            ext = Path(f).suffix.lower()
            if ext:
                exts.add(ext)
        return f"Используемые типы файлов в проекте (стек): {', '.join(sorted(exts))}"

    @mcp.resource("repo://conventions")
    def get_repo_conventions_resource() -> str:
        """Возвращает код-стайл и конвенции репозитория (поиск файлов .editorconfig, lint, configs)."""
        if not indexer.repos:
            return "Нет добавленных репозиториев"
        
        repo_path = Path(indexer.repos[0])
        conventions = []
        
        for config_name in ['.editorconfig', 'pyproject.toml', 'package.json', '.eslintrc', '.prettierrc', 'tox.ini', '.gitignore']:
            config_path = repo_path / config_name
            if config_path.exists():
                try:
                    content = config_path.read_text(encoding='utf-8')
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
    def inject_context(include_map: bool = True, include_stack: bool = True, include_conventions: bool = False):
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
            context.append("=== Конвенции проекта (repo://conventions) ===\n" + get_repo_conventions_resource())
            
        return {"context": "\n\n".join(context)}
