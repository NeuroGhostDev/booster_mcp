# Booster MCP

主要文档为英文版：[README.md](README.md)。
其他语言：[Русский](README.ru.md) | [English](README.md)。

Booster MCP 是面向 coding agent 的本地 MCP server 和 Cognitive Runtime。
它构建受预算约束、可检查的软件项目模型，包括 repository map、symbols、
import/call graph、git context、project memory、diagnostics 和 validation
loop。

## Booster 解决的问题

普通 coding agent 往往只搜索几个文件、生成 patch，然后停止。Booster 在
编辑前提供：

- 架构地图和技术栈；
- semantic 与 lexical retrieval；
- impact analysis 和依赖图；
- git history/blame；
- fail-closed diagnostics；
- project memory 和项目规则；
- patch 后的 validation plan 与执行。

## 安装

需要 Python 3.11–3.13、Git 和 `uv`。

```bash
git clone https://github.com/NeuroGhostDev/Booster-mcp.git
cd Booster-mcp
uv sync --locked --extra dev
```

检查安装：

```bash
booster control doctor --project .
booster expand --profile balanced
```

## AI Agent Bootstrap

当 agent 通过 GitHub URL 打开仓库时，先读取 [`AGENTS.md`](AGENTS.md) 和
[`RECOMENDET_PROMPT.md`](RECOMENDET_PROMPT.md)，然后执行 onboarding：

```bash
uv sync --locked --extra dev
uv run python -c "from skill_installer import install_bundled_skills; print(install_bundled_skills())"
uv run booster expand --profile balanced .
uv run booster control connect --client vscode --scope workspace --project . --with-repository --force
uv run booster control doctor --project .
```

对于 Claude Desktop，使用 `--client claude --scope user`。仓库不会静默修改
host application 的隐藏 system prompt；portable 机制是 `AGENTS.md`、
`RECOMENDET_PROMPT.md`、bundled skills 和选定的 MCP 配置。

## 连接 MCP

为 VS Code workspace 创建连接：

```bash
booster control connect --client vscode --scope workspace --project .
```

创建 user 级连接：

```bash
booster control connect --client vscode --scope user --project .
```

启动 MCP 后，让 agent 对当前项目调用 `add_repo`。

## Context Injection

推荐的 onboarding 流程：

```text
add_repo(repo_path="C:\\projects\\my_app")
index_status(repo_path="C:\\projects\\my_app")
inject_context(include_map=true, include_stack=true, include_conventions=true)
```

复杂修改前使用：

```text
preflight_analysis(task="Refactor AuthService", target="AuthService", repo="<repo>")
impact_analysis(target="AuthService", repo="<repo>", max_depth=3)
collect_diagnostics(paths=["src/auth/service.py"], repo="<repo>")
```

## 大型仓库索引

索引采用 job-based contract，不会阻塞 read-only MCP tools。为兼容旧客户端，
`add_repo(wait=true)` 仍然接受该参数，但会立即返回。

```text
add_repo(repo_path="C:\\projects\\large_monorepo", wait=true)
index_status(job_id="idx_...")
wait_until_ready(job_id="idx_...", timeout_seconds=30)
cancel_index(job_id="idx_...")
```

状态包含 `job_id`、phase（`scan`、`parse`、`graph`、`embed`、`finalize`）、
`processed`、`total`、elapsed time、ETA、`last_progress_at`、generation ID
和 stale state。新 generation 构建期间，read/search 方法继续使用最后一个
ready snapshot。

扫描配置：

| Profile | 深度 | 文件数 | 源码大小 |
| --- | ---: | ---: | ---: |
| `quick` | 6 | 250 | 8 MiB |
| `balanced` | 12 | 800 | 32 MiB |
| `deep` | 20 | 3,000 | 128 MiB |

## 生成的 artifacts

`.agents/booster/` 中包含：

- `repo_map_architecture.md`：带 diversity 和 coverage 的 bounded macro map；
- `repo_map_symbols.md`：带单文件 cap 的详细 symbol map；
- `index_health.json`：generation、coverage、skipped/stale/deleted paths；
- `repo_map.md`：向后兼容的 architecture map 副本；
- `code_city.html`、`scan_config.json`、`scan_report.json`；
- `snapshots/`：immutable history。

大型 LEGION 模块不会被排除，但不会挤掉 frontend、control plane、entrypoints
和 contracts 在 bounded architecture map 中的覆盖。

## Booster Home 与 Nemotron

Home 是 coding agent 与 inference backend 之间的本地 OpenAI-compatible
gateway。使用 LM Studio 中的 Nemotron 4B：

```bash
booster home \
  --base-url http://127.0.0.1:1234/v1 \
  --model nvidia/nemotron-3-nano-4b \
  --api-key lm-studio \
  --project .
```

Home 提供 `/v1/models`、`/v1/chat/completions`、`/v1/responses`、`/health`
和 `/booster/status`。provider-specific 字段 `reasoning_content` 会被保留。
当 output budget 太小时，Nemotron 可能返回空的 `message.content` 和
`finish_reason=length`；这种情况不会被伪装成普通成功回答。

loopback bind 不需要 gateway token。non-loopback bind 必须配置至少 16 个字符
的 `home.auth_token`，请求使用 `Authorization: Bearer ...`。

检查 Home：

```bash
booster home --base-url http://127.0.0.1:1234/v1 \
  --model nvidia/nemotron-3-nano-4b --api-key lm-studio \
  --probe-generation doctor --json
```

## 验证

```bash
uv lock --check
uv run python -m pytest tests -q
uv run ruff check .
uv run python -m compileall -q booster_home indexing_jobs.py server.py
uv build
```

更多信息：

- [Cookbook](COOKBOOK.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API](docs/API.md)
- [Release checklist](docs/RELEASE.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Marketplace](MARKETPLACE.md)
