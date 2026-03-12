# Публикация в MCP Маркетплейсы

Booster MCP полностью совместим с популярными каталогами MCP серверов (Smithery, Glama и Claude Desktop).

В этом документе описаны шаги для публикации сервера.

## 1. Публикация в Smithery

[Smithery](https://smithery.ai) позволяет пользователям устанавливать сервера одним кликом через CLI.

Убедитесь, что ваш проект соответствует манифесту `smithery.yaml`. Этот файл уже должен быть в корне репозитория, либо настройте CLI для автогенерации.

Для автоматической публикации добавьте Badge в ваш `README.md`:

```markdown
[![smithery badge](https://smithery.ai/badge/booster-mcp)](https://smithery.ai/server/booster-mcp)
```

Или предложите установку через npx:

```bash
npx -y @smithery/cli install booster-mcp --client claude
```

## 2. Публикация в Glama

[Glama](https://glama.ai) — каталог агентов и MCP серверов.

Для публикации в Glama вам нужно:

1. Авторизоваться на портале `glama.ai/mcp`.
2. Добавить ссылку на GitHub репозиторий.
3. Glama автоматически спарсит ваш `README.md` и инструментарий.

Убедитесь, что у вас есть значок Glama в README:

```markdown
<a href="https://glama.ai/mcp/servers/n6l9tqkh8f"><img width="380" height="200" src="https://glama.ai/mcp/servers/n6l9tqkh8f/badge" alt="Booster MCP Server badge" /></a>
```

*(Замените ID на тот, что выдаст вам панель Glama)*

## 3. Конфигурация для Claude Desktop

Booster поддерживает прямую интеграцию в **Claude Desktop** через добавление JSON-записи в конфиг.

```json
"Booster": {
  "command": "python",
  "args": ["-m", "booster_mcp.server"]
}
```

## 4. Требования перед релизом

- Обязательное описание всех Tools в коде (документированные `args` и `description`).
- Рабочие примеры и юзкейсы в `COOKBOOK.md`.
- Версионирование через GitHub Releases.
- Все встроенные зависимости должны быть прописаны в `requirements.txt` или `pyproject.toml`.
