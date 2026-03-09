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
2. Сними масштаб через repo_stats.
3. Получи структурную карту через get_repo_map.
4. Для больших проектов построй визуальную карту через get_code_city.
5. Найди точки входа через semantic_search и find_symbol.
6. Сохрани выводы в project_memory.

## Базовая последовательность

```text
add_repo("<repo>")
repo_stats()
get_repo_map("<repo>")
get_code_city("<repo>")
semantic_search("application entry point")
semantic_search("router handler controller")
find_symbol("main")
list_configs("<repo>")
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
