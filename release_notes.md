# Booster MCP v3.0 Release 🚀

We are thrilled to announce a massive update for Booster MCP, taking semantic code analysis, project mapping, and visualization to a whole new level!

What's new in this version:

## 🛡️ Smart Context Protection & Indexing Optimization (Smart Parser)
We've seriously upgraded how your repositories are scanned:
- **Auto-generated `.ignore`**: When adding a new project (`add_repo`), the server now automatically generates an ignore file, cutting off heavy and noisy directories out of the box: `node_modules`, `venv`, `build`, `target`, `.next`, etc.
- **Smart Traversal (os.walk + MAX_DEPTH)**: The parser has been rewritten to physically skip ignored directories instead of filtering them later. We also introduced a hard `MAX_DEPTH` limit (15) to prevent infinite directory recursion.
*Result: Lightning-fast indexing, huge CPU savings, and a crystal-clear context (repo map) for your LLMs with zero noise.*

## 🌆 Cyberpunk Code City 3D (Neon v3)
Your `code_city.html` will never look the same:
- **Neon & Cyberpunk Aesthetic**: A completely redesigned 3D visualization. Dark cosmic background, glowing "neon" edges for buildings (files) and connection lines.
- **Bloom Post-Processing**: We mapped `UnrealBloomPass` to create a realistic, immersive glowing effect.
- **Glassmorphism UI**: Statistics panels, settings menu, and legends now feature a sleek, semi-transparent "glass" design with blur effects.
- **Dynamic Scaling**: Building heights scale dynamically based on your selected metric (lines of code, complexity, or class count) with smooth animations. Isometric camera makes navigation both intuitive and stunning.

## ⚡ Auto-Generated & Cached Artifacts
- No need to manually request `get_repo_map` or `get_code_city` anymore! After full indexing completes, the server **automatically** generates your `repo_map.md` and `code_city.html` in the background.
- These artifacts are securely cached in a hidden `.agents/booster/` directory within your project. MCP tools now read from this cache instantly!

## 🤖 Context7 Integration & Built-in Agent Skills
- **Context7 Bridge (`fetch_stack_docs`)**: Instantly inject the latest, up-to-date documentation for your frameworks directly into your LLM’s context before writing a single line of code.
- **Auto-Installation for Agent Skills**: On server startup, Booster MCP automatically syncs a suite of 7 powerful, built-in guided agents (`booster-onboard`, `booster-feature-add`, `booster-bug-hunt`, etc.) straight into your `~/.agents/skills` directory!

## 📦 One-Click Installers
Getting started is easier than ever with our new **One-Click Installers** for Windows (PowerShell) and macOS/Linux (Bash). A single command downloads the embedding models, sets up the virtual environment, and boots the server alongside all skills. Check the updated `README.md` for the commands.

Upgrade now and boost your productivity! 🚀
