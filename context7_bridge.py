from pathlib import Path

def setup_context7_bridge(mcp, indexer):
    """
    Мост для интеграции с MCP-сервером Context7.
    Предоставляет агенту инструменты для автоматического получения актуальных доков по стеку.
    """
    
    @mcp.tool()
    def fetch_stack_docs():
        """
        Анализирует технологический стек проекта и возвращает рекомендации агенту:
        какие библиотеки искать через mcp_context7_resolve-library-id
        для подгрузки актуальной документации и сохранения ее в `[repoPATH]/.agents/booster/stack_docs.md`.
        """
        if not indexer.repos:
            return {"error": "Нет проиндексированных репозиториев для анализа стека."}
            
        # 1. Анализируем типы файлов
        exts = set()
        for f in indexer.symbols.keys():
            ext = Path(f).suffix.lower()
            if ext:
                exts.add(ext)
                
        # 2. Формируем список потенциальных библиотек
        libraries = []
        if set(['.js', '.jsx', '.ts', '.tsx']) & exts:
            libraries.extend(["react", "next.js", "typescript", "node.js", "express"])
        if '.py' in exts:
            libraries.extend(["fastapi", "django", "pytest", "pydantic", "sqlalchemy"])
        if '.go' in exts:
            libraries.extend(["go", "gin", "gorm"])
        if '.rs' in exts:
            libraries.extend(["rust", "tokio", "serde"])
        if '.java' in exts:
            libraries.extend(["java", "spring boot"])
            
        # Убираем дубликаты
        libraries = list(set(libraries))
            
        return {
            "instruction": "Для каждой из рекомендованных библиотек: 1) Вызовите mcp_context7_resolve-library-id, 2) Получите доки через mcp_context7_query-docs, 3) Сохраните результат и важные концепции в файл `[repo_path]/.agents/booster/stack_docs.md`.",
            "recommended_libraries": libraries,
            "detected_extensions": list(exts)
        }
