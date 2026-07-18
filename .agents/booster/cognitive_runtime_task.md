# Booster Cognitive Runtime: постановка задачи

## Контекст

Booster MCP уже умеет строить repo map, индексировать код через Tree-sitter,
делать semantic/hybrid search, хранить простую project memory и отдавать
агентам call/import graph. Следующий шаг: превратить Booster из сервера поиска
контекста в слой восприятия и инженерного контроля для coding agents.

## Цель

Добавить в Booster рабочий Cognitive Runtime, который собирает для агента одну
картину проекта перед изменением кода и после него:

- AST/Code Knowledge Graph: область влияния символов, callers/callees, imports,
  affected files и тестовые зоны.
- Git Intelligence: история, blame и объяснение происхождения кода рядом с
  файлом или символом.
- Long-term Project Memory: структурированные факты проекта с категориями,
  confidence, источником и поиском по задаче.
- Validation Loop: команды проверки, diagnostics, ошибки компилятора/типов и
  следующий инженерный шаг.
- IDE/Compiler Diagnostics Layer: Python syntax, Ruff, Pyright, TypeScript,
  Rust и security scanners как headless-инструменты, без зависимости от UI
  VS Code.

## MVP в этом изменении

1. Не поднимать внешний Neo4j/Memgraph. Использовать текущие `RepoIndexer.symbols`
   и `Graphs.call_graph/import_graph` как in-memory knowledge graph.
2. Добавить новый модуль `cognitive_runtime.py` с MCP tools:
   - `impact_analysis`
   - `git_intelligence`
   - `remember_project_fact`
   - `project_memory_recall`
   - `collect_diagnostics`
   - `preflight_analysis`
   - `validation_loop_plan`
   - `run_validation_checks`
3. Подключить tools в `server.py` без изменения существующих API.
4. Вплести новые tools в bundled skills, чтобы агенты вызывали их до и после
   feature/refactor/debug/review работ.
5. Покрыть новый слой тестами без обязательного наличия внешних бинарников
   `pyright`, `tsc`, `cargo`, `bandit`.
6. Diagnostics должны работать fail-closed: timeout, crash или непарсимый вывод
   внешнего анализатора превращается в `error` finding, а не в тихий `passed`.

## Расширение после MVP

- Заменить in-memory graph storage адаптером Neo4j/Memgraph без изменения MCP
  контрактов.
- Добавить полноценный LSP client для diagnostics/references/rename поверх
  Pyright, typescript-language-server, rust-analyzer, gopls и clangd.
- Индексировать PR/issue metadata из GitHub/GitLab и связывать `Commit -> PR ->
Issue -> Symbol`.
- Сделать repair loop с автоматическим повтором `diagnostics -> patch -> tests`
  на стороне агента.
