# Booster MCP

**A Cognitive Runtime for coding agents.**

Booster builds a live world model of your software system so AI coding agents
can understand architecture, history, diagnostics, project rules, and validation
requirements before they edit code.

Most agents already have hands: they can write patches quickly. What they lack
is perception. They do not consistently see the architecture, old decisions,
compiler errors, dependency impact, or the tests that should be run next.
Booster is the local MCP layer that gives them that perception.

## The Problem

Large codebases do not break agents because there are too many files. They
break agents because there is no compact map of the system.

Without Booster, a coding agent usually does this:

```text
User request -> grep/search -> read a few files -> generate patch -> stop
```

That misses the things senior engineers rely on every day:

- Which symbols call this code?
- What files and tests are affected if this interface changes?
- Why was this code written this way in git history?
- What project-specific rules must not be violated?
- Are there existing type, lint, compiler, or security diagnostics?
- Did the patch pass the right validation loop?

Booster changes the loop:

```text
User request
  -> project memory
  -> repo map and hybrid search
  -> AST impact graph
  -> git history/blame
  -> compiler/linter/security diagnostics
  -> validation plan
  -> agent patch
  -> validation checks
```

## What Booster Gives Agents

| Agent pain                                | Booster capability                                                                           | Result                                                        |
| ----------------------------------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| Blind search through huge repos           | Bounded scanning, Repo Map, hybrid semantic + lexical retrieval                              | Less context waste, faster orientation                        |
| Text snippets without architecture        | Tree-sitter symbols, call/import graph, impact analysis                                      | Agents see blast radius before editing                        |
| No memory between sessions                | Structured project memory in `.agents/booster/memory.json`                                   | Project rules and decisions survive restarts                  |
| No idea why code exists                   | Git log and blame through `git_intelligence`                                                 | Debugging includes historical intent                          |
| Ignored red squiggles                     | Fail-closed diagnostics with Python syntax, Ruff, Pyright, TypeScript, Rust, Bandit, Semgrep | Agents see errors before and after patches                    |
| Patch generation without engineering loop | `validation_loop_plan` and `run_validation_checks`                                           | Plan -> implement -> validate -> repair                       |
| Reindexing noise from dependencies        | Shared scan and watcher ignore rules                                                         | `.venv`, caches, and dependency folders stay out of the model |

## Why This Is Not Just Another MCP Search Server

Search is only one part of the job. Booster combines retrieval with an
engineering control loop:

- **World model**: repo map, symbols, imports, calls, artifacts, and Code City.
- **Impact model**: `impact_analysis` separates internal affected symbols from
  unresolved external calls and estimates blast radius.
- **History model**: `git_intelligence` connects files and symbols to commits
  and blame context.
- **Memory model**: `remember_project_fact` and `project_memory_recall` store
  architecture rules, decisions, and project constraints.
- **Diagnostic model**: `collect_diagnostics` normalizes compiler, linter, and
  security findings. Tool failures are treated as validation failures, not as
  success.
- **Validation model**: `run_validation_checks` combines diagnostics and focused
  test commands in one result for the agent to repair.

Booster's position is simple:

> Give coding agents the same perception layer that human engineers get from
> an IDE, git history, architecture knowledge, and test feedback.

## What It Provides

- Hybrid retrieval: normalized FAISS cosine search, BM25 lexical search, and
  reciprocal-rank fusion through `hybrid_search`.
- Bounded scanning for large repositories with reproducible scan profiles.
- Generated artifacts in `.agents/booster/`: `repo_map.md`, `code_city.html`,
  `scan_config.json`, and `scan_report.json`.
- Context injection through `repo://map`, `repo://stack`,
  `repo://conventions`, and `repo://artifacts`.
- Architecture and debugging tools: symbols, import and call graphs,
  flipcharts, Code City, and repository diagnostics.
- Cognitive Runtime tools for impact analysis, git history/blame, structured
  project memory, fail-closed compiler/linter diagnostics, security checks,
  and validation loops.
- Twelve bundled workflow skills that are synced to `~/.agents/skills`.
- `booster control`, a cross-platform post-install control surface for MCP
  clients, scan settings, diagnostics, and launcher management.

## Quick Cognitive Runtime Example

Ask your agent to connect the repository and run a preflight before editing:

```text
add_repo(repo_path="C:\\projects\\my-app")
repo_stats()
preflight_analysis(
  task="Refactor AuthService token validation",
  target="AuthService",
  paths=["src/auth/service.py"],
  repo="C:\\projects\\my-app"
)
```

The agent receives:

- indexing status for the repository;
- relevant project memory and constraints;
- affected callers, callees, files, and suggested tests;
- git history and blame context when requested;
- existing diagnostics in the touched files;
- the recommended validation order.

After the patch:

```text
run_validation_checks(
  paths=["src/auth/service.py"],
  commands=["pytest tests/auth -q"],
  repo="C:\\projects\\my-app"
)
```

That result tells the agent whether to repair diagnostics, fix tests, or move
to final review.

## Requirements

- Python 3.11 through 3.13. Python 3.12 is recommended.
- Git.
- Internet access on the first run to download the embedding model.

## Install

The installers prefer `uv` and the committed `uv.lock`. If `uv` is not
available, they create a compatible virtual environment and install the local
package with pip.

### Windows

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/NeuroGhostDev/Booster-mcp/main/install.ps1 -OutFile install.ps1
.\install.ps1
```

### macOS and Linux

```bash
curl -fsSL https://raw.githubusercontent.com/NeuroGhostDev/Booster-mcp/main/install.sh | bash
```

Each installer creates a `booster` launcher in the user-local bin directory:

- Windows: `%USERPROFILE%\.local\bin\booster.cmd`
- macOS and Linux: `~/.local/bin/booster`

The installer adds that directory to the user PATH. Open a new terminal after
installation if the current shell does not yet find `booster`.

### Development Installation

```bash
git clone https://github.com/NeuroGhostDev/Booster-mcp.git
cd Booster-mcp
uv sync --locked --extra dev
```

Without `uv`, create a Python 3.12 virtual environment and install the project:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

On Windows, activate with `\.venv\Scripts\Activate.ps1` and use
`\.venv\Scripts\booster.exe` until the launcher is installed.

## Connect Booster to VS Code

Run the control menu from the repository you want to manage:

```text
booster control
```

For automation, use one of the two explicit connection scopes.

### Workspace Connection

Use this for a repository-specific server. It writes `.vscode/mcp.json`, starts
Booster with that repository in `REPOS`, and is the recommended default for a
project that you control.

```text
cd path/to/project
booster control connect --client vscode --scope workspace --project .
booster expand --profile balanced
```

### User Connection

Use this once when you want Booster to appear in every VS Code workspace. It
writes the VS Code user `mcp.json`, uses the exact Python from the Booster
installation, and deliberately starts without a fixed `REPOS` value. This
prevents a global server from repeatedly indexing the last project you opened.

```text
booster control connect --client vscode --scope user --project .
```

After the global server starts, ask the agent to call `add_repo` with the
repository currently being worked on. `add_repo` starts indexing in the
background by default and `repo_stats` reports the current indexing status. Pass
`wait=true` only when you intentionally want a blocking call. To intentionally
bind a user-level server to one repository, pass `--with-repository`.

VS Code keeps workspace and user MCP configuration separately. After adding or
changing a server, run `MCP: List Servers`, select `Booster`, then start or
restart it and accept the trust prompt. If the entry is still not visible, run
`Developer: Reload Window` and inspect `MCP: List Servers` > `Booster` >
`Show Output`.

Every configuration write is atomic. The previous file is saved beside it with
the `.booster.bak` suffix.

## Booster Control

`booster control` opens an interactive menu with connection management, scan
profiles, artifact refresh, diagnostics, server removal, and launcher updates.
The same operations are available as non-interactive commands:

```text
# Show the active runtime, client entry, scan policy, and artifacts.
booster control status --client vscode --scope workspace --project .

# Add or remove a client entry.
booster control connect --client vscode --scope workspace --project .
booster control disconnect --client vscode --scope workspace --project .

# Connect Claude Desktop in the user profile.
booster control connect --client claude --scope user --project .

# Inspect and persist the bounded scan policy.
booster control scan --project .
booster control scan --project . --profile deep --max-files 2000

# Verify Python, FastMCP, FAISS, BM25, and embedding dependencies.
booster control doctor --project .
```

## Bounded Repository Scanning

Run `booster expand` before attaching a large repository. It saves the scan
policy and generates the initial map without requiring a live MCP connection.

```text
booster expand --profile balanced
```

| Profile    | Depth | Source files | Selected source size | Best for                 |
| ---------- | ----: | -----------: | -------------------: | ------------------------ |
| `quick`    |     6 |          250 |                8 MiB | Fast initial orientation |
| `balanced` |    12 |          800 |               32 MiB | Most repositories        |
| `deep`     |    20 |        3,000 |              128 MiB | Large monorepos          |

The scanner prioritizes conventional source roots, ignores generated and
dependency directories by default, and records every limit decision in
`.agents/booster/scan_report.json`. Add local exclusions in `.boosterignore`
when a directory is irrelevant to the current task.

## Cognitive Runtime Workflow

Use this flow when the agent is about to change code:

1. **Recall project rules** with `project_memory_recall`.
2. **Find the target** with `hybrid_search`, `semantic_search`, or
   `find_symbol`.
3. **Estimate blast radius** with `impact_analysis`.
4. **Check history** with `git_intelligence` when code looks surprising.
5. **Collect diagnostics** with `collect_diagnostics` for the files in scope.
6. **Patch narrowly** using the project's existing patterns.
7. **Validate** with `run_validation_checks` and repair the same slice until it
   passes or the hypothesis is wrong.

Typical preflight:

```text
project_memory_recall(query="refactor billing invoice flow", repo="<repo>")
impact_analysis(target="InvoiceService", repo="<repo>", max_depth=3)
git_intelligence(symbol="InvoiceService", repo="<repo>", limit=8)
collect_diagnostics(paths=["src/billing/invoice.py"], repo="<repo>")
```

Typical post-patch validation:

```text
run_validation_checks(
  paths=["src/billing/invoice.py"],
  commands=["pytest tests/billing -q"],
  repo="<repo>"
)
```

### Diagnostics Are Fail-Closed

Booster treats diagnostics as engineering evidence. A diagnostic tool that
times out, crashes, or returns unparseable output is reported as an `error`
finding. This prevents agents from mistaking a broken validation run for a
clean codebase.

| Language or area      | Current checks                                               |
| --------------------- | ------------------------------------------------------------ |
| Python                | in-process syntax compile, Ruff, Pyright when installed      |
| TypeScript/JavaScript | `tsc --noEmit` when `tsconfig.json` and `tsc` exist          |
| Rust                  | `cargo check --message-format=json` when `Cargo.toml` exists |
| Security              | Bandit and Semgrep when installed                            |
| Tests                 | Any focused command passed to `run_validation_checks`        |

## Example Use Cases

### Before a Refactor

```text
impact_analysis(target="AuthService", repo="<repo>", max_depth=4)
git_intelligence(symbol="AuthService", repo="<repo>")
collect_diagnostics(paths=["src/auth/service.py"], repo="<repo>")
```

The agent can answer: what calls it, what it calls, which files are affected,
what tests look relevant, and whether there are already red diagnostics.

### During a Bug Hunt

```text
analyze_error("<stacktrace>")
git_intelligence(path="src/payments/locks.py", symbol="payment_lock")
flipchart_call_graph(symbol="payment_lock", max_depth=4)
```

The agent can combine stack traces, call graph context, and the historical
reason a suspicious line exists.

### For Long-Term Project Knowledge

```text
remember_project_fact(
  category="architecture",
  fact="Frontend talks to backend only through the BFF layer",
  confidence=0.95,
  source="repo_map+impact_analysis"
)
```

Future sessions can recall that fact before editing API or frontend code.

## Typical Agent Workflow

1. Connect the repository with `booster control` or `add_repo`.
2. Check `repo_stats` until indexing is completed for workflows that need a
   fresh graph.
3. Run `get_repo_artifacts` and `get_repo_map` before broad file reads.
4. Use `semantic_search` and `hybrid_search` to find behavior and exact
   identifiers.
5. Use the matching workflow skill: `booster-onboard`, `booster-bug-hunt`,
   `booster-feature-add`, `booster-refactor`, or `booster-review`.
6. Run `preflight_analysis` or `impact_analysis` before changing shared code.
7. Use graph and flipchart tools only after a relevant symbol is identified.
8. Validate the smallest affected test or command after each implementation
   step.

Bundled skills:

- `booster-architecture-map`
- `booster-bug-hunt`
- `booster-context-inject`
- `booster-cognitive-runtime`
- `booster-deep-dive`
- `booster-feature-add`
- `booster-flipchart`
- `booster-mcp-workflow`
- `booster-onboard`
- `booster-project-memory`
- `booster-refactor`
- `booster-review`

## Key MCP Tools

| Area                    | Examples                                                                                                                                                                              |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Repository lifecycle    | `add_repo`, `remove_repo`, `reindex_repo`, `list_repos`, `repo_stats`                                                                                                                 |
| Search and navigation   | `semantic_search`, `hybrid_search`, `find_symbol`                                                                                                                                     |
| Context and artifacts   | `inject_context`, `get_repo_artifacts`, `get_repo_map`, `get_code_city`                                                                                                               |
| Reasoning and debugging | `flipchart_quick_debug`, `flipchart_call_graph`, `flipchart_sequence_diagram`                                                                                                         |
| Cognitive runtime       | `preflight_analysis`, `impact_analysis`, `git_intelligence`, `remember_project_fact`, `project_memory_recall`, `collect_diagnostics`, `validation_loop_plan`, `run_validation_checks` |
| Workflow support        | `list_agent_skills`, `install_agent_skills`, `fetch_stack_docs`                                                                                                                       |

## Roadmap

Booster already uses an in-memory Tree-sitter symbol/call/import graph. The
next production steps are:

- Persist the knowledge graph to Neo4j or Memgraph for cross-session graph
  queries and deeper dependency traversal.
- Add a headless LSP client for Pyright, typescript-language-server,
  rust-analyzer, gopls, clangd, and Java language servers.
- Link commits to PRs and issues so `git_intelligence` can explain not only
  what changed, but why it changed.
- Add richer validation recipes for Docker Compose, health checks, and service
  logs.
- Expand bundled skills into architecture, debugging, memory, and quality
  packs for agent-specific workflows.

## Troubleshooting

### Booster Is Missing from VS Code

Check both configuration scopes:

```text
booster control status --client vscode --scope workspace --project .
booster control status --client vscode --scope user --project .
```

Only a workspace entry is visible in that workspace. A user entry is visible in
all workspaces. Use `MCP: List Servers` to start, trust, restart, or inspect
the server. Use `MCP: Open User Configuration` to open the exact global file
that VS Code is reading.

### `No module named rank_bm25`

The client is starting an old system Python rather than Booster's environment.
Repair the project environment and reconnect it through Booster Control:

```text
uv sync --locked --extra dev
booster control doctor --project .
booster control connect --client vscode --scope user --project . --force
```

### The Scan Is Too Narrow

Inspect the report, then select a broader profile or explicit limits:

```text
booster control scan --project . --profile deep
booster expand --profile deep
```

## Validation

```text
uv lock --check
python -m pytest tests -q
ruff check cli.py control.py tests
```

See [COOKBOOK.md](COOKBOOK.md) for detailed workflows and
[MARKETPLACE.md](MARKETPLACE.md) for publishing and client distribution.

## License

MIT
