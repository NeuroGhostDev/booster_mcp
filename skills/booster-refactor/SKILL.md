---
name: booster-refactor
description: |
  Безопасный рефакторинг с анализом области влияния и обязательной верификацией после изменений.
---

# booster Refactor

## Цель

Менять структуру кода без изменения поведения.

## Алгоритм

```text
code_grep("<symbol>")
call_graph("<symbol>")
import_graph("<file>")
read_with_context("<file>", line=<line>, context=80)
git_log("<file>", limit=15)
find_duplicates(min_lines=4)
run_command("<tests before>")
run_command("<tests after>")
git_diff("<repo or file>")
```

## Правила

- сначала определить все usages
- не смешивать рефакторинг и новую фичу
- при переносе символа оставлять совместимый импорт, если нужно
- проверять тесты до и после

## Когда остановиться

- если зона влияния неожиданно выросла
- если нет тестов и меняется критичный путь
