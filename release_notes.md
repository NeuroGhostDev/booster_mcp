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
- **Auto-Installation for Agent Skills**: On server startup, Booster MCP synchronizes eleven guided workflow skills (`booster-onboard`, `booster-feature-add`, `booster-bug-hunt`, `booster-review`, and more) into `~/.agents/skills`.

## Cross-Platform Booster Control

- **`booster control`**: an interactive and scriptable post-install control surface for VS Code and Claude Desktop MCP entries, scan policies, artifact refresh, diagnostics, safe removal, and launcher updates.
- **Correct runtime by construction**: generated client entries use the exact Python environment that installed Booster, avoiding failures from unrelated system Python installations.
- **Workspace or user scope**: workspace connections bind `REPOS` to one project; user connections are portable and let the agent add the active project when needed.
- **Safe configuration writes**: client files are updated atomically and backed up with a `.booster.bak` suffix.

## One-Click Installers

The Windows PowerShell and macOS/Linux Bash installers set up the virtual environment, dependencies, bundled skills, and a user-local `booster` launcher. Check [README.md](README.md) for the commands and use `booster control doctor --project .` after installation.

Upgrade now and boost your productivity! 🚀
