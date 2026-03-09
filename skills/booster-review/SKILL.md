---
name: booster-review
description: |
  Глубокий code review с проверкой безопасности, архитектуры, производительности и качества.
---

# booster Review

## Цель

Найти реальные риски, а не просто стилистические замечания.

## Алгоритм

```text
git_diff("<path>")
git_log("<path>", limit=5)
read_with_context("<file>", line=1, context=200)
find_symbol("<main changed symbol>")
call_graph("<main changed symbol>")
import_graph("<file>")
external_deps(file="<file>")
code_grep("TODO|FIXME|HACK|password|secret|eval|exec")
run_command("<tests>")
```

## Проверяй явно

- инъекции
- секреты в коде
- нарушения слоёв
- ломаную обратную совместимость
- синхронный I/O на горячих путях

## Формат вывода

1. критичные риски
2. важные замечания
3. остаточные риски и пробелы тестов
