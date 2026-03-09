---
name: booster-feature-add
description: |
  Безопасное добавление новой фичи в существующую архитектуру через паттерны уже написанного кода.
---

# booster Feature Add

## Цель

Перед реализацией найти правильное место, стиль и аналог существующей фичи.

## Алгоритм

```text
project_memory("get", "architecture_overview", repo="<repo>")
semantic_search("<feature description>")
find_symbol("<related class or service>")
read_with_context("<analog file>", line=<line>, context=60)
call_graph("<neighbor symbol>")
import_graph("<target file>")
external_deps("<neighbor symbol>")
find_duplicates(min_lines=3)
```

## До написания кода выясни

- куда добавлять реализацию
- есть ли аналог или шаблон
- какие зависимости уже используются
- нужен ли тест и конфиг

## После реализации

```text
find_symbol("<new symbol>")
run_command("<project tests>")
project_memory("set", "feature_<name>", "...", repo="<repo>")
```
