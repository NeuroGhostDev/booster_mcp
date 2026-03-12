---
name: booster-onboard
description: |
  Быстрый онбординг в незнакомую кодовую базу через booster MCP.
  Используй первым при работе с новым репозиторием.
---

# booster Onboard

## Цель

Быстро построить карту проекта, не читая всю кодовую базу подряд.

## Алгоритм

1. Добавь репозиторий через add_repo.
2. 🚀 **СРАЗУ ЖЕ** вызови `inject_context()` чтобы получить карту проекта (RepoMap) и список конвенций.
3. Вызови `fetch_stack_docs()`, чтобы понять какие библиотеки использует проект и подгрузить их доки (через mcp context7).
4. Сними масштаб через repo_stats().
5. Для больших проектов построй визуальную карту через get_code_city.
6. Найди точки входа через semantic_search и find_symbol.
7. Сохрани выводы в project_memory.

## Базовая последовательность

```text
add_repo("<repo>")
inject_context()
fetch_stack_docs()
repo_stats()
get_code_city()
semantic_search("application entry point")
list_configs()
project_memory("set", "architecture_overview", "...", repo="<repo>")
```

## Что извлечь

- точки входа
- ключевые модули
- внешний стек
- конфиги и env
- горячие зоны проекта

## Антипаттерны

- не читать подряд десятки файлов
- не пропускать repo_map
- не начинать багфикс без первичного онбординга
