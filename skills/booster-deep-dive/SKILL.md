---
name: booster-deep-dive
description: |
  Глубокий архитектурный анализ: потоки данных, зависимости, критические пути и узкие места.
---

# booster Deep Dive

## Цель

Понять реальную архитектуру и путь данных от входа до результата.

## Алгоритм

```text
repo_stats()
get_repo_map("<repo>")
get_code_city("<repo>")
semantic_search("<user flow>")
find_symbol("<entry handler>")
flipchart_create_session("arch_<flow>", ["<entry>", "<service>", "<repo>"])
flipchart_sequence_diagram("<entry>", depth=7)
flipchart_call_graph("<entry>", max_depth=5)
import_graph("<critical file>")
external_deps(file="<critical file>")
find_duplicates(min_lines=5)
```

## Результат

- слои системы
- критические пути
- внешние зависимости
- горячие точки
- архитектурный долг

## Обязательное действие

Сохраняй выводы в project_memory, иначе они потеряются между сессиями.
