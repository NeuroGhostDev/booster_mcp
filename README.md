# Booster MCP

Booster is a local MCP server for understanding large codebases before making
changes. It combines bounded repository scanning, semantic and lexical code
search, repository maps, call graphs, Code City visualizations, and workflow
skills for onboarding, debugging, feature work, refactoring, and review.

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
- Eleven bundled workflow skills that are synced to `~/.agents/skills`.
- `booster control`, a cross-platform post-install control surface for MCP
  clients, scan settings, diagnostics, and launcher management.

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
repository currently being worked on. To intentionally bind a user-level server
to one repository, pass `--with-repository`.

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

| Profile | Depth | Source files | Selected source size | Best for |
| --- | ---: | ---: | ---: | --- |
| `quick` | 6 | 250 | 8 MiB | Fast initial orientation |
| `balanced` | 12 | 800 | 32 MiB | Most repositories |
| `deep` | 20 | 3,000 | 128 MiB | Large monorepos |

The scanner prioritizes conventional source roots, ignores generated and
dependency directories by default, and records every limit decision in
`.agents/booster/scan_report.json`. Add local exclusions in `.boosterignore`
when a directory is irrelevant to the current task.

## Typical Agent Workflow

1. Connect the repository with `booster control` or `add_repo`.
2. Run `get_repo_artifacts` and `get_repo_map` before broad file reads.
3. Use `semantic_search` and `hybrid_search` to find behavior and exact
   identifiers.
4. Use the matching workflow skill: `booster-onboard`, `booster-bug-hunt`,
   `booster-feature-add`, `booster-refactor`, or `booster-review`.
5. Use graph and flipchart tools only after a relevant symbol is identified.
6. Validate the smallest affected test or command after each implementation
   step.

Bundled skills:

- `booster-architecture-map`
- `booster-bug-hunt`
- `booster-context-inject`
- `booster-deep-dive`
- `booster-feature-add`
- `booster-flipchart`
- `booster-mcp-workflow`
- `booster-onboard`
- `booster-project-memory`
- `booster-refactor`
- `booster-review`

## Key MCP Tools

| Area | Examples |
| --- | --- |
| Repository lifecycle | `add_repo`, `remove_repo`, `reindex_repo`, `list_repos`, `repo_stats` |
| Search and navigation | `semantic_search`, `hybrid_search`, `find_symbol` |
| Context and artifacts | `inject_context`, `get_repo_artifacts`, `get_repo_map`, `get_code_city` |
| Reasoning and debugging | `flipchart_quick_debug`, `flipchart_call_graph`, `flipchart_sequence_diagram` |
| Workflow support | `list_agent_skills`, `install_agent_skills`, `fetch_stack_docs` |

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
