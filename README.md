# 🚀 Booster MCP — Semantic Code Intelligence for Large Codebases

[![MCP](https://img.shields.io/badge/MCP-server-blue)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🎯 What You Get

**Booster MCP turns complex codebases into understandable systems.**

You spend less time searching and more time building. Instead of:
- ❌ Manually grepping through thousands of files
- ❌ Getting lost in unfamiliar architectures
- ❌ Debugging by guessing

You get:
- ✅ **Instant semantic understanding** — ask questions, get answers across your entire codebase
- ✅ **Visual architecture maps** — see your code as a 3D "Code City"
- ✅ **Automatic context injection** — include exactly what the AI needs to fix bugs or add features
- ✅ **Debugging superpowers** — flipchart sessions with call graphs, sequence diagrams, and session notes
- ✅ **7 battle-tested agent skills** — pre-built workflows for onboarding, refactoring, bug hunting, and code review

### Real-World Impact

| Problem | Old Way | With Booster |
|---------|---------|--------------|
| New developer onboarding | 2-3 days of grep | 30 min interactive map + context |
| Finding related code | Manual search | Semantic search + symbol graph |
| Debugging production issues | Stack traces → manual tracing | `analyze_error()` → call graph → fix |
| Code review bottlenecks | Hours of manual review | Semantic + dependency analysis |

---

## ⚡ Quick Start (1 minute)

### One-Click Install

**macOS / Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/NeuroGhostDev/Booster-mcp/main/install.sh | bash
```

**Windows (PowerShell):**
```powershell
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/NeuroGhostDev/Booster-mcp/main/install.ps1" -OutFile "install.ps1" | .\install.ps1
```

### First Command

```python
add_repo("C:\\my-project")
get_code_city()  # Opens 3D visualization in browser
```

That's it. Your codebase is now AI-searchable.

---

## 💎 Features at a Glance

### 🔍 **Semantic Search** (Not Just Grep)
- Vector-powered code search understands intent, not just keywords
- Find "authentication flow" and get relevant login, OAuth, token validation code
- Works across multiple languages

### 🗺️ **Code City 3D**
- Visual representation of your project structure
- Buildings = files (height = complexity, color = language)
- Instantly spot architectural patterns and dependencies

### 📊 **Repository Maps**
- One-page project overview for onboarding
- Auto-generated, always in sync
- Includes conventions, stack, and module boundaries

### 🐛 **Flipchart Debugging**
- Create debug sessions with call graphs and sequence diagrams
- Mermaid-powered visualizations
- Add notes and track hypotheses across symbols

### 🤖 **7 Built-in Agent Skills**
- `booster-onboard` — new codebase? Start here
- `booster-context-inject` — give AI exactly what it needs
- `booster-bug-hunt` — stack trace → diagnosis → fix
- `booster-feature-add` — find patterns, add consistent code
- `booster-deep-dive` — understand architecture
- `booster-refactor` — impact analysis + change automation
- `booster-review` — semantic code review

### 🔗 **Context Injection**
```
repo://map          → Repository structure
repo://stack        → Dependencies and frameworks
repo://conventions  → Code patterns and standards
```

Auto-sync with live documentation via `fetch_stack_docs()`.

### ⚙️ **Incremental Indexing**
- Watchdog monitors changes
- No manual reindex needed
- Multi-repo support without server restart

---

## 📦 What's Included

| Component | Purpose |
|-----------|---------|
| **FastMCP Server** | Core tool definitions and routing |
| **Vector Indexer** | FAISS-backed semantic search across code |
| **Graph Engine** | Call graphs, import graphs, dependency analysis |
| **Code City Visualizer** | 3D HTML visualization of codebase |
| **Agent Skills** | 7 pre-built workflows for common tasks |
| **Web UI** | Manage repos, generate visualizations, inspect maps |
| **Flipchart** | Debug sessions with Mermaid diagrams |
| **Toolkit** | Grep, git, command execution, error analysis |

---

## 🛠️ Installation

### Requirements
- Python 3.11+
- Git
- Internet (first run downloads embedding model)

### Full Manual Install (all platforms)

**Clone & Setup:**
```bash
git clone https://github.com/NeuroGhostDev/Booster-mcp.git
cd Booster-mcp
python3.11 -m venv .venv
source .venv/bin/activate  # or .\.venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt
```

**Start:**
```bash
python server.py
```

### Configure Your MCP Client

Add to your `.claude_desktop_config.json` (Claude Desktop, Cline, etc):

**macOS/Linux:**
```json
{
  "mcpServers": {
    "Booster": {
      "command": "/home/user/Booster-mcp/.venv/bin/python",
      "args": ["/home/user/Booster-mcp/server.py"]
    }
  }
}
```

**Windows (use absolute paths):**
```json
{
  "mcpServers": {
    "Booster": {
      "command": "C:\\Users\\YourName\\Booster-mcp\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\YourName\\Booster-mcp\\server.py"]
    }
  }
}
```

---

## 🚀 Common Workflows

### Onboard a New Project
```python
add_repo("C:\\project")
repo_stats()           # Quick metrics
get_repo_map()         # Architecture overview
semantic_search("main entry point")
find_symbol("main")    # Navigate to key functions
```

### Debug a Production Error
```python
analyze_error("TypeError: 'NoneType' object is not subscriptable")
flipchart_quick_debug("handler_function", max_depth=3)
read_with_context("auth.py", line=42, context=10)
git_diff("auth.py")    # See recent changes
```

### Add a Feature Safely
```python
semantic_search("similar feature pattern")
find_symbol("existing_feature")
flipchart_sequence_diagram("existing_feature", depth=5)
# Now safe to implement
```

### Code Review with Superpowers
```python
flipchart_call_graph("modified_function", max_depth=5)
external_deps("modified_function")
find_duplicates(min_lines=5)
```

---

## 📚 Full Documentation

- **[COOKBOOK.md](COOKBOOK.md)** — Deep-dive recipes and advanced usage
- **[MARKETPLACE.md](MARKETPLACE.md)** — Publish to MCP catalogs

---

## 🎓 System Instructions for Maximum Power

Add this to your MCP client for best results:

```
MCP Usage Policy:
- New codebase? Use onboard skill first
- Production error? Use bug-hunt skill
- Architecture question? Use deep-dive skill
- Adding feature? Use feature-add skill + inject context
- Refactoring? Use refactor skill + analyze impact
- Code review? Use review skill + semantic analysis

Always prefer semantic tools over grep for understanding.
```

[See full system instructions in README]

---

## 🛠️ All Available Tools

### Repository Management
- `add_repo(path)` — Index a new repository
- `remove_repo(path)` — Stop tracking
- `reindex_repo(path)` — Force re-index
- `list_repos()` — See active repos
- `repo_stats()` — Size, symbols, metrics

### Search & Navigation
- `semantic_search(query)` — Find code by meaning
- `find_symbol(name)` — Locate functions, classes

### Context Injection
- `inject_context()` — Auto-build AI context
- `fetch_stack_docs()` — Live dependency docs

### Debugging
- `flipchart_quick_debug(symbol)` — Instant graphs
- `flipchart_call_graph(symbol)` — Show callers/callees
- `flipchart_sequence_diagram(symbol)` — Flow diagram
- `analyze_error(stacktrace)` — Error analysis

### Utilities
- `code_grep(pattern)` — Smart grep
- `read_with_context(file, line)` — Show code + context
- `git_log(path)` — See history
- `run_command(cmd)` — Execute tools
- `find_duplicates()` — Code duplication
- `external_deps(symbol)` — See dependencies

### Visualization
- `get_code_city()` — 3D visualization
- `get_repo_map()` — Architecture map

---

## 🌍 Language Support

- Python
- JavaScript / TypeScript
- Rust
- Go
- Java
- C / C++

---

## 🧪 Testing

```bash
python test_mcp.py        # Basic tests
python test_all.py        # Full suite
```

---

## ❓ FAQ

**Q: Will this slow down my codebase?**  
A: No. Indexing is separate. Your code runs normally.

**Q: Does it work with private repos?**  
A: Yes. Everything runs locally. No data leaves your machine.

**Q: Which AI clients are supported?**  
A: Any MCP-compatible client (Claude Desktop, Cline, Continue, etc).

**Q: Can I index multiple repos at once?**  
A: Yes. `add_repo()` as many as you want. No restart needed.

**Q: What if my repo is 1M+ lines?**  
A: Works fine. Semantic indexing is built for scale. Use `.ignore` to skip heavy directories.

---

## 📖 Detailed Docs & Guides

- **[COOKBOOK.md](COOKBOOK.md)** — Recipes, examples, advanced techniques
- **[MARKETPLACE.md](MARKETPLACE.md)** — Publish to Smithery, Glama

---

## 🤝 Contributing

1. Fork it
2. Branch: `git checkout -b feature/my-feature`
3. Commit: `git commit -m "Add feature"`
4. Test: `python test_all.py`
5. Push & open PR

---

## 📄 License

MIT — Use freely, commercial or otherwise.

---

## 🎯 Next Steps

1. **Install now:** Run the one-click installer
2. **Try it:** `add_repo()` + `get_code_city()`
3. **Read cookbook:** Advanced workflows and examples
4. **Share feedback:** [GitHub Issues](https://github.com/NeuroGhostDev/booster_mcp/issues)

---

**Made for developers who demand more from their tools.** ⚡
