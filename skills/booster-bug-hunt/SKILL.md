---
name: booster-bug-hunt
description: |
  Систематическая охота за багами: от stacktrace до корневой причины.
  Используй при ошибках, падениях тестов и странном поведении.
---

# booster Bug Hunt

## Цель

Сузить поиск от симптома до конкретного символа, строки и причины.

## Если есть stacktrace

```text
analyze_error("<stacktrace>")
flipchart_create_session("bug_<id>", ["<symbol1>", "<symbol2>"])
flipchart_call_graph("<symbol>", max_depth=4)
read_with_context("<file>", line=<line>, context=25)
code_grep("<error fragment>")
git_diff("<file>")
git_log("<file>", limit=10)
```

## Если есть только описание поведения

```text
semantic_search("<symptom>")
find_symbol("<suspected symbol>")
flipchart_quick_debug("<symbol>", max_depth=4)
external_deps("<symbol>")
```

## Проверки

- regression через git_diff и git_log
- внешний сервис через external_deps
- дубли логики через find_duplicates

## Финал

Сохрани причину и фикс в project_memory.
