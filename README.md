# Booster MCP

[![MCP](https://img.shields.io/badge/MCP-server-blue)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Booster MCP is an MCP server for semantic code analysis, repository mapping, and navigation across large codebases. It is built for AI agents and developers who need fast project onboarding, symbol discovery, structural visualization, and practical debugging tools.

![Code City 3D Visualization - Your repository as a virtual city](assets/code_city.png)

## 📖 Documentation & Guides

- **[COOKBOOK.md](COOKBOOK.md)** — Detailed recipes, practical use-cases, and prompt examples for working with the server.
- **[MARKETPLACE.md](MARKETPLACE.md)** — Instructions for publishing to MCP catalogs (Smithery, Glama).

## Features

- Semantic code search powered by vector embeddings
- Context Injection via MCP resources (`repo://map`, `repo://stack`, `repo://conventions`)
- Context7 integration via `fetch_stack_docs` for up-to-date dependency documentation
- Symbol lookup for functions, classes, and methods
- Repository map generation for compact project context
- Call graph and import graph exploration
- Code City 3D visualization with a built-in web UI
- Flipchart debugging with Mermaid diagrams and session notes
- Toolkit utilities for grep, git inspection, command execution, duplicate search, and project memory
- Incremental indexing with automatic updates via watchdog
- Dynamic repository management without restarting the server
- Bundled agent skills synced to `.agents/skills` on startup

## Bundled Agent Skills

Booster MCP ships with built-in skills for working with large codebases. On startup, the server synchronizes them into the local agent skills directory.

Included skills:

- `booster-onboard`
- `booster-context-inject`
- `booster-bug-hunt`
- `booster-feature-add`
- `booster-deep-dive`
- `booster-refactor`
- `booster-review`

Related MCP tools:

- `list_agent_skills()`
- `install_agent_skills(overwrite: bool = True)`

Default install location:

- Windows: `%USERPROFILE%\\.agents\\skills`
- macOS: `~/.agents/skills`
- Linux: `~/.agents/skills`

## Requirements

- Python 3.11+
- Git
- Internet access on first run to download the `all-MiniLM-L6-v2` embedding model

## Installation

### One-Click Installers (Recommended)

The fastest way to install Booster MCP and automatically set up all bundled Agent Skills.

**macOS / Linux / Debian / Ubuntu / iOS (Termux/a-shell):**

```bash
curl -fsSL https://raw.githubusercontent.com/NeuroGhostDev/Booster-mcp/main/install.sh -o install.sh
bash install.sh
```

**Windows (PowerShell):**

```powershell
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/NeuroGhostDev/Booster-mcp/main/install.ps1" -OutFile "install.ps1"
.\install.ps1
```

### Manual Installation

#### Windows

```powershell
git clone https://github.com/NeuroGhostDev/Booster-mcp.git
cd Booster-mcp

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation scripts, allow local scripts once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Start the server:

```powershell
python server.py
```

### macOS

```bash
git clone https://github.com/NeuroGhostDev/Booster-mcp.git
cd Booster-mcp

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If `python3.11` is missing:

```bash
brew install python@3.11
```

Start the server:

```bash
python server.py
```

### Linux

```bash
git clone https://github.com/NeuroGhostDev/Booster-mcp.git
cd Booster-mcp

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If the venv module is missing:

```bash
sudo apt update
sudo apt install python3.11 python3.11-venv
```

Start the server:

```bash
python server.py
```

### Quick Install Without a Virtual Environment

```bash
git clone https://github.com/NeuroGhostDev/Booster-mcp.git
cd Booster-mcp
pip install -r requirements.txt
```

Note: the first model download can take a few minutes.

## MCP Client Configuration

Add Booster MCP to your MCP client configuration.

### Windows example

```json
{
  "mcpServers": {
    "Booster": {
      "command": "py",
      "args": ["-3.11", "C:\\Users\\Whoami\\Booster-mcp\\server.py"],
      "env": {}
    }
  }
}
```

### Windows with virtual environment

```json
{
  "mcpServers": {
    "Booster": {
      "command": "C:\\Users\\Whoami\\Booster-mcp\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\Whoami\\Booster-mcp\\server.py"],
      "env": {
        "CITY_PORT": "8080"
      }
    }
  }
}
```

### Linux or macOS example

```json
{
  "mcpServers": {
    "Booster": {
      "command": "/home/user/Booster-mcp/.venv/bin/python",
      "args": ["/home/user/Booster-mcp/server.py"],
      "env": {
        "CITY_PORT": "8080"
      }
    }
  }
}
```

Before strat using Booster MCP, make sure to add that block of system instructions to your MCP client configuration.

## Block of system instructions

```text
MCP usage policy

- If a semantic repository analysis MCP server is available, prefer it over plain text search for onboarding, architecture analysis, dependency tracing, debugging, refactoring, and code review.
- When entering a new repository or returning after a long break, start with repository onboarding:
  inspect repository stats, repository map, configuration files, conventions, stack context, and indexed structure before making implementation decisions.
- For bug investigation, stack traces, failing tests, and strange runtime behavior, start with semantic error analysis, dependency tracing, contextual file reads, and graph-based debugging before broad manual grep.
- For architecture questions, feature planning, and change impact analysis, prefer repository map, symbol search, external dependency analysis, call graph, sequence diagram, and context injection.
- Before adding a feature, first search for existing patterns, conventions, related symbols, and neighboring implementations in the repository to avoid duplicate architecture and inconsistent code paths.
- Before refactoring, use semantic tooling to identify the impact radius, related symbols, configuration touchpoints, and affected dependencies.
- When performing code review, prioritize semantic review of bugs, regressions, security risks, dependency boundaries, and performance issues before giving summaries.
- If stack or dependency documentation can be fetched dynamically, retrieve up-to-date docs before making framework-specific or library-specific decisions.
- Use repository memory only for stable, verified architectural facts, conventions, and operational knowledge. Do not store assumptions as facts.
- If the repository is not indexed or the index is stale, refresh or rebuild the semantic index before deep analysis.

Booster MCP skill routing policy

- New repository or unfamiliar codebase -> use onboard flow
- Bug, exception, failing tests, broken runtime -> use bug-hunt flow
- Architecture, data flow, dependency analysis -> use deep-dive flow
- New feature in existing system -> use feature-add flow
- Structural cleanup or behavior-preserving rewrite -> use refactor flow
- Code review or audit request -> use review flow
- Large task requiring context bootstrapping -> inject repository context before implementation
- Framework-sensitive work -> fetch current stack documentation before changing code

Tool preference policy

- Prefer semantic repository tools over grep when the goal is understanding structure rather than matching text.
- Prefer contextual reads over opening many small disconnected snippets.
- Prefer symbol- and graph-based navigation over manual search when evaluating impact or tracing behavior.
- Prefer stack documentation retrieval before making assumptions about external libraries, frameworks, or APIs.
```

Use absolute paths for both the Python interpreter and `server.py`.

## What Happens on Startup

When `server.py` starts, Booster MCP:

- initializes the MCP server
- starts the Code City web UI in a background thread
- synchronizes bundled agent skills into the agent skills directory
- indexes repositories from the `REPOS` environment variable, if provided

Restart your MCP client after updating its configuration.

## Available Tools

### Repository Management

- `add_repo(repo_path: str)`
- `remove_repo(repo_path: str)`
- `reindex_repo(repo_path: str)`
- `list_repos()`
- `repo_stats()`
- `get_repo_map(repo_path: str = None)`

### Search and Navigation

- `semantic_search(query: str)`
- `find_symbol(name: str)`

### Context Injection (v3.0)

- `inject_context(include_map: bool = True, include_stack: bool = True, include_conventions: bool = False)`
- `fetch_stack_docs()`

### Flipchart Debugging

- `flipchart_quick_debug(symbol: str, max_depth: int = 3)`
- `flipchart_create_session(session_id: str, symbols: list[str])`
- `flipchart_add_note(session_id: str, label: str, content: str, symbols: list[str] = None)`
- `flipchart_get_board(session_id: str)`
- `flipchart_call_graph(symbol: str, max_depth: int = 5)`
- `flipchart_sequence_diagram(symbol: str, depth: int = 5)`

### Toolkit

- `code_grep(pattern: str, file_pattern: str = "*", ignore_case: bool = True, max_results: int = 100)`
- `read_with_context(file: str, line: int, context: int = 20)`
- `read_file(file: str, start: int = 0, end: int = 100)`
- `git_diff(path: str, commit: str = "HEAD", staged: bool = False)`
- `git_log(path: str, limit: int = 10)`
- `run_command(cmd: str, cwd: str = None, timeout: int = 30000)`
- `analyze_error(error_text: str, symbols: list[str] = None)`
- `list_configs(repo: str = None)`
- `project_memory(action: str, key: str, value: str = None, repo: str = None)`
- `compare_symbols(symbol: str, file1: str, file2: str)`
- `find_duplicates(min_lines: int = 5, max_results: int = 50)`
- `external_deps(symbol: str = None, file: str = None)`

### Visualization and Skills

- `get_code_city(repo_path: str = None, output_file: str = "code_city.html")`
- `list_agent_skills()`
- `install_agent_skills(overwrite: bool = True)`

## Code City 3D

`get_code_city()` generates a 3D HTML visualization where:

- building height represents file size and complexity
- color represents language or file type
- districts represent folders or modules
- links represent imports and cross-file relationships

Typical usage:

```text
add_repo("C:\\my-project")
get_code_city()
```

The output file is automatically generated and cached as `.agents/booster/code_city.html` within the selected repository. Repo Map and Project Memory are also cached in the `.agents/booster` directory.

## Web UI

Booster MCP also starts an HTTP interface for managing repositories and viewing Code City.

Start it manually if needed:

```bash
python city_server.py --port 8080
```

Main capabilities:

- repository list and basic statistics
- add and remove repositories
- reindex repositories
- generate and open Code City views
- inspect RepoMap output in the browser

Main endpoints:

- `GET /api/repos`
- `GET /api/stats`
- `GET /api/code_city`
- `GET /api/repo_map`
- `POST /api/repos/add`
- `POST /api/repos/remove`
- `POST /api/repos/reindex`
- `POST /api/repos/generate_city`

## Ignore Files

Global ignores can be defined in `~/.ignore`:

```text
__pycache__/
*.pyc
.venv/
venv/
node_modules/
.idea/
.vscode/
target/
vendor/
```

Project-specific ignores can be defined in `.ignore` at the repository root:

```text
build/
*.bin
*.gguf
logs/
models/
```

## Example Workflows

### Onboard a New Repository

```text
add_repo("C:\\my-project")
repo_stats()
get_repo_map()
semantic_search("authentication flow")
find_symbol("main")
```

### Investigate an Error

```text
analyze_error("TypeError: 'NoneType' object is not subscriptable")
code_grep("logger\\.error", file_pattern="*.py")
read_with_context("C:\\project\\auth.py", line=42, context=10)
git_diff("C:\\project\\auth.py")
```

### Debug a Complex Flow with Flipchart

```text
flipchart_create_session("auth_debug", ["main_handler", "auth_verify", "db_connect"])
flipchart_add_note("auth_debug", "Token issue", "Token is not revalidated after reconnect")
flipchart_get_board("auth_debug")
```

### Inspect a Large Project Visually

```text
add_repo("D:\\workSpace\\coreconn")
get_code_city()
```

## Project Structure

```text
server.py          FastMCP server and tool definitions
indexer.py         indexing pipeline and component orchestration
parser_router.py   tree-sitter parser routing
graphs.py          call and import graph storage
chunker.py         semantic chunking
embedder.py        embedding generation
vector_index.py    FAISS-backed vector index
watcher.py         incremental indexing via watchdog
repomap.py         compact repository map generation
flipchart.py       Mermaid diagrams and debug sessions
visualizer.py      Code City 3D generation
city_server.py     HTTP UI for repository and city management
toolkit.py         grep, git, command, memory, duplicates, dependency tools
skill_installer.py bundled skill synchronization
```

## Supported Languages

Current parsing support depends on the installed tree-sitter language pack, with this repository primarily targeting:

- Python
- JavaScript
- TypeScript
- Rust
- Go
- Java
- C
- C++

## Testing

Basic commands:

```bash
python test_mcp.py
python test_all.py
```

Targeted sanity checks:

```bash
python -c "from indexer import RepoIndexer; i = RepoIndexer(['.']); i.full_index(); print(len(i.symbols))"
python -c "from toolkit import CodeToolkit; from indexer import RepoIndexer; i = RepoIndexer(['.']); t = CodeToolkit(i, ['.']); print(t.code_grep('def ', max_results=5))"
python -c "from visualizer import CodeCityVisualizer; from indexer import RepoIndexer; i = RepoIndexer(['.']); v = CodeCityVisualizer(i); print(v.generate_visualization('.', 'test.html'))"
```

## Troubleshooting

### `ModuleNotFoundError: No module named 'fastmcp'`

Install dependencies into the same interpreter used to start the server:

```bash
/path/to/python -m pip install -r requirements.txt
```

### Empty Search Results

Possible causes:

- no repository has been added yet, so run `add_repo()` first
- the provided path is wrong or not absolute
- the target files are excluded by ignore rules

### `run_command` Fails

Common causes:

- invalid `cwd`
- timeout too low for the command
- command requires interactive input

### Mermaid Diagrams Do Not Render

Use a Markdown renderer with Mermaid support. GitHub and GitLab support Mermaid natively, while VS Code may require an extension.

## License

MIT

## Contributing

1. Fork the repository.
2. Create a feature branch.
3. Make your changes.
4. Run the relevant tests.
5. Open a pull request.
