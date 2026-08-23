# Booster MCP

Английская версия является основной документацией: [README.md](README.md).
Также доступны [English](README.md) и [简体中文](README.zh-CN.md).

Booster MCP — локальный MCP-сервер и Cognitive Runtime для coding agents. Он
строит ограниченную и проверяемую модель проекта: архитектурную карту, символы,
графы импортов и вызовов, git-контекст, project memory, diagnostics и validation
loop.

## Что решает Booster

Без Booster агент обычно ищет несколько файлов, пишет patch и останавливается.
Booster добавляет перед изменением кода:

- карту репозитория и стек;
- semantic и lexical retrieval;
- impact analysis и граф зависимостей;
- git history/blame;
- fail-closed diagnostics;
- project memory и правила проекта;
- план и запуск валидации после patch.

## Установка

Требуются Python 3.11–3.13, Git и `uv`.

```bash
git clone https://github.com/NeuroGhostDev/Booster-mcp.git
cd Booster-mcp
uv sync --locked --extra dev
```

Проверка установки:

```bash
booster control doctor --project .
booster expand --profile balanced
```

## Подключение MCP

Для workspace-подключения VS Code:

```bash
booster control connect --client vscode --scope workspace --project .
```

Для user-подключения:

```bash
booster control connect --client vscode --scope user --project .
```

После запуска MCP попросите agent вызвать `add_repo` для текущего проекта.

## Context Injection

Основной onboarding flow:

```text
add_repo(repo_path="C:\\projects\\my_app")
index_status(repo_path="C:\\projects\\my_app")
inject_context(include_map=true, include_stack=true, include_conventions=true)
```

Для сложного изменения сначала используйте:

```text
preflight_analysis(task="Refactor AuthService", target="AuthService", repo="<repo>")
impact_analysis(target="AuthService", repo="<repo>", max_depth=3)
collect_diagnostics(paths=["src/auth/service.py"], repo="<repo>")
```

## Индексация больших репозиториев

Индексация job-based и не блокирует read-only MCP tools. `add_repo(wait=true)`
сохраняет совместимую сигнатуру, но также возвращает сразу.

```text
add_repo(repo_path="C:\\projects\\large_monorepo", wait=true)
index_status(job_id="idx_...")
wait_until_ready(job_id="idx_...", timeout_seconds=30)
cancel_index(job_id="idx_...")
```

Статус содержит `job_id`, phase (`scan`, `parse`, `graph`, `embed`,
`finalize`), `processed`, `total`, elapsed time, ETA, `last_progress_at`,
generation ID и stale state. Пока строится новая generation, read/search методы
используют последний готовый snapshot.

Профили scanner:

| Профиль | Глубина | Файлы | Размер исходников |
| --- | ---: | ---: | ---: |
| `quick` | 6 | 250 | 8 MiB |
| `balanced` | 12 | 800 | 32 MiB |
| `deep` | 20 | 3,000 | 128 MiB |

## Артефакты

В `.agents/booster/` создаются:

- `repo_map_architecture.md` — bounded macro map с diversity и coverage;
- `repo_map_symbols.md` — подробная symbol map с cap на файл;
- `index_health.json` — generation, coverage, skipped/stale/deleted paths;
- `repo_map.md` — backward-compatible копия architecture map;
- `code_city.html`, `scan_config.json`, `scan_report.json`;
- `snapshots/` — immutable history.

Giant-модули не исключаются, но не могут вытеснить frontend, control plane,
entrypoints и contracts из bounded architecture map.

## Booster Home и Nemotron

Home — локальный OpenAI-compatible gateway между coding agent и inference
backend. Для LM Studio с Nemotron 4B:

```bash
booster home \
  --base-url http://127.0.0.1:1234/v1 \
  --model nvidia/nemotron-3-nano-4b \
  --api-key lm-studio \
  --project .
```

Home предоставляет `/v1/models`, `/v1/chat/completions`, `/v1/responses`,
`/health` и `/booster/status`. Поля `reasoning_content` сохраняются. При малом
output budget Nemotron может вернуть пустой `message.content` и
`finish_reason=length`; это не считается успешным обычным ответом.

Loopback bind не требует gateway token. Для non-loopback bind нужен
`home.auth_token` длиной минимум 16 символов, а запросы должны использовать
`Authorization: Bearer ...`.

Проверка:

```bash
booster home --base-url http://127.0.0.1:1234/v1 \
  --model nvidia/nemotron-3-nano-4b --api-key lm-studio \
  --probe-generation doctor --json
```

## Валидация

```bash
uv lock --check
uv run python -m pytest tests -q
uv run ruff check .
uv run python -m compileall -q booster_home indexing_jobs.py server.py
uv build
```

Подробности:

- [Cookbook](COOKBOOK.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API](docs/API.md)
- [Release checklist](docs/RELEASE.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Marketplace](MARKETPLACE.md)
