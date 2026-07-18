# Booster MCP v3.1 Cognitive Runtime Release

Booster MCP now moves beyond repository search into a Cognitive Runtime for
coding agents. The goal is simple: agents should not edit code while blind to
architecture, history, diagnostics, project rules, and validation feedback.

## Cognitive Runtime for Coding Agents

New MCP tools turn Booster into a preflight and validation layer:

- `preflight_analysis` combines project memory, impact analysis, and
  diagnostics before a patch.
- `impact_analysis` traverses the Tree-sitter symbol/call/import graph and
  estimates blast radius.
- `git_intelligence` exposes git log and blame context for files and symbols.
- `remember_project_fact` and `project_memory_recall` store and retrieve
  long-term architecture rules and project decisions.
- `collect_diagnostics` normalizes compiler, linter, and security findings.
- `validation_loop_plan` and `run_validation_checks` guide agents through
  Plan -> Implement -> Validate -> Repair.

## Fail-Closed Diagnostics

Diagnostics now behave like engineering evidence, not best-effort decoration:

- Python syntax is checked in-process with `compile(...)`, avoiding subprocess
  hangs for basic syntax validation.
- Ruff diagnostics are collected when Ruff is available.
- Pyright, TypeScript, Rust, Bandit, and Semgrep output is normalized when the
  corresponding tool exists.
- Tool timeouts, crashes, and unparseable output become `error` findings instead
  of false success.

## Cleaner Impact Graphs

`impact_analysis` now separates internal affected symbols from unresolved
external calls. This keeps builtins and test helpers such as `str`, `tool`, or
`write_text` from inflating the architectural blast radius while still showing
them as external calls.

## Watcher Ignore Rules

The file watcher now reuses the same ignore rules as the bounded repository
scanner. Incremental updates no longer pollute `RepoIndexer.symbols` with
changes from `.venv`, caches, dependency directories, or generated folders after
a clean initial scan.

## MCP Runtime Hardening

- `add_repo` now starts indexing in the background by default. This keeps long
  scan/embedding work out of the MCP stdio request and avoids crash-on-cancel
  failures such as `AssertionError: Request already responded to` in the MCP
  transport. Pass `wait=true` only for an intentionally blocking run.
- `repo_stats` now reports per-repository indexing job status.
- `RepoIndexer.index_repo` indexes one repository at a time instead of forcing
  every `add_repo` path through a full reindex of all repositories.
- Code City Web UI now logs the real bound port when `CITY_PORT=0` is used,
  instead of printing `http://localhost:0`.
- Web UI reindex now uses `RepositoryScanner` ignore rules instead of a stale
  `IGNORED_DIRS` import.
- Toolkit git helpers now build path-limited `git diff` and `git log` commands
  correctly with `cmd.extend(["--", path])`.

## Documentation and Skills

- Added the `booster-cognitive-runtime` skill.
- Updated feature, bug-hunt, refactor, review, deep-dive, and memory skills to
  call Cognitive Runtime tools.
- Reworked README positioning around agent pain points, product differentiation,
  diagnostics, and validation loops.
- Added marketplace copy for MCP catalogs and launch posts.
- Added cookbook recipes for preflight analysis and post-patch validation.

Validation for this release:

```text
python -m pytest tests -q
ruff check cognitive_runtime.py watcher.py server.py city_server.py indexer.py graphs.py chunker.py parser_router.py embedder.py toolkit.py skill_installer.py context_provider.py context7_bridge.py flipchart.py tests/test_cognitive_runtime.py tests/test_watcher.py tests/test_runtime_hardening.py
python -m py_compile cognitive_runtime.py watcher.py server.py city_server.py indexer.py toolkit.py
```

---

# Booster MCP v3.0 Release

We are thrilled to announce a massive update for Booster MCP, taking semantic code analysis, project mapping, and visualization to a whole new level!

What's new in this version:

## Smart Context Protection and Bounded Indexing

We've seriously upgraded how your repositories are scanned:

- **Auto-generated `.ignore`**: When adding a new project (`add_repo`), the server now automatically generates an ignore file, cutting off heavy and noisy directories out of the box: `node_modules`, `venv`, `build`, `target`, `.next`, etc.
- **Bounded traversal**: The shared repository scanner uses deterministic breadth-first selection with explicit depth, directory, file-count, individual-file, and total-size budgets.
- **Scan profiles**: `quick`, `balanced`, and `deep` persist in `.agents/booster/scan_config.json` and are reused by RepoMap, indexing, and reindexing.
  _Result: predictable coverage for large repositories and an explainable `scan_report.json`._

## 🌆 Cyberpunk Code City 3D (Neon v3)

Your `code_city.html` will never look the same:

- **Neon & Cyberpunk Aesthetic**: A completely redesigned 3D visualization. Dark cosmic background, glowing "neon" edges for buildings (files) and connection lines.
- **Bloom Post-Processing**: We mapped `UnrealBloomPass` to create a realistic, immersive glowing effect.
- **Glassmorphism UI**: Statistics panels, settings menu, and legends now feature a sleek, semi-transparent "glass" design with blur effects.
- **Dynamic Scaling**: Building heights scale dynamically based on your selected metric (lines of code, complexity, or class count) with smooth animations. Isometric camera makes navigation both intuitive and stunning.

## ⚡ Auto-Generated & Cached Artifacts

- No need to manually request `get_repo_map` or `get_code_city` anymore! After full indexing completes, the server **automatically** generates your `repo_map.md` and `code_city.html` in the background.
- These artifacts are securely cached in a hidden `.agents/booster/` directory within your project. MCP tools now read from this cache instantly!

## Context7 Integration and Built-in Agent Skills

- **Context7 Bridge (`fetch_stack_docs`)**: Instantly inject the latest, up-to-date documentation for your frameworks directly into your LLM’s context before writing a single line of code.
- **Auto-Installation for Agent Skills**: On server startup, Booster MCP synchronizes twelve guided workflow skills (`booster-onboard`, `booster-feature-add`, `booster-bug-hunt`, `booster-review`, `booster-cognitive-runtime`, and more) into `~/.agents/skills`.

## Cross-Platform Booster Control

- **`booster control`**: an interactive and scriptable post-install control surface for VS Code and Claude Desktop MCP entries, scan policies, artifact refresh, diagnostics, safe removal, and launcher updates.
- **Correct runtime by construction**: generated client entries use the exact Python environment that installed Booster, avoiding failures from unrelated system Python installations.
- **Workspace or user scope**: workspace connections bind `REPOS` to one project; user connections are portable and let the agent add the active project when needed.
- **Safe configuration writes**: client files are updated atomically and backed up with a `.booster.bak` suffix.

## One-Click Installers

The Windows PowerShell and macOS/Linux Bash installers set up the virtual environment, dependencies, bundled skills, and a user-local `booster` launcher. Check [README.md](README.md) for the commands and use `booster control doctor --project .` after installation.

Upgrade now and boost your productivity! 🚀
