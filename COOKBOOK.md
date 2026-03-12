# Booster MCP Cookbook

Welcome to the **Booster MCP Cookbook**! This guide contains best practices, recipes, and examples of how AI agents and developers can maximize the capabilities of Booster MCP v3.0.

Booster MCP transforms your AI agent into a "Senior Engineer" capable of quickly understanding architecture, finding deep context, building 3D visualizations, and integrating up-to-date library documentation (Context7).

---

## 📖 Recipe 1: Instant Onboarding in a New Project

When an agent first encounters a large project, it doesn't need to read hundreds of files blindly. It needs a "map of the territory" and a view of the "city."

**Step 1. Add Repository to the Index**
```text
Agent Prompt: Call the `add_repo` tool with the absolute path to the project.
Example: add_repo(repo_path="C:\\projects\\my_large_app")
```
*What happens:* Booster indexes the code, builds call and import graphs, and automatically generates artifacts: `.agents/booster/code_city.html` and `.agents/booster/repo_map.md`. It also auto-generates a `.ignore` file to skip noisy directories like `node_modules` and `venv`.

**Step 2. Request the Repository Map**
```text
Agent Prompt: Call `get_repo_map(repo_path="C:\\projects\\my_large_app")`
```
The agent receives a condensed Markdown tree of the project highlighting crucial classes and functions (similar to Aider's RepoMap). This saves context window space and provides instant structural understanding.

**Step 3. Visualize in 3D (for the User)**
```text
Agent Prompt: Tell the user to open the generated `code_city.html` file in their browser.
```
The user will see a 3D city where building height equals file complexity, and color represents the programming language. This helps visually identify "hot" and complex zones in the codebase.

---

## 🔍 Recipe 2: Smart Search & Dependency Analysis

Forget blind `grep`. Use semantic search and AST analysis.

**Scenario:** You need to find where user authentication occurs in the project.
```text
Agent Prompt: Call `semantic_search(query="user authentication logic JWT")`
```
Booster will find relevant code snippets by *meaning*, even if the exact string "JWT" is missing from the code.

**Scenario:** The function `verify_token` was found. You need to see who calls it and what it calls.
```text
Agent Prompt: Call `flipchart_call_graph(symbol="verify_token", max_depth=3)`
```
Booster returns a Mermaid call graph diagram. The agent renders it, and the developer instantly understands the authorization flow.

---

## 🧠 Recipe 3: Context Injection

In version 3.0, Booster introduces the concept of **Active Context**. Agents can gather project knowledge so they don't forget the core ideas upon restarting.

**Working with Project Memory (`project_memory`):**
When an agent makes an important architectural decision (e.g., "In this project, we use Pydantic v2 and dependency injection"), it should record it:
```text
Agent Prompt: Call `project_memory(action="set", key="architecture_rules", value="Use Pydantic v2 and DI container. No singletons.")`
```
On the next run, the `booster-onboard` skill automatically pulls these rules and injects them into the agent's system prompt.

---

## 📚 Recipe 4: Working with Context7 (Fresh External Docs)

A common agent problem: hallucinating function parameters for new library versions. 
Booster MCP solves this with the Context7 bridge.

**Scenario:** The project uses `FastAPI`, and the agent isn't sure how to configure `Lifespan` events in the latest versions.

**Solution:**
```text
Agent Prompt: Call `mcp_context7_resolve-library-id(query="fastapi lifespan events", libraryName="fastapi")`
```
The agent fetches up-to-date documentation from the Context7 cloud and generates correct, working code on the first try.

Additionally, Booster MCP provides the `fetch_stack_docs` tool, which analyzes `requirements.txt` / `package.json` and automatically downloads documentation for key stack dependencies into `stack_docs.md`.

---

## 📊 Recipe 5: Debugging Sessions with Flipchart

Flipchart is the virtual whiteboard for your agent.

1. **Create a Debug Session:**
   ```text
   Call: flipchart_create_session(session_id="bug_142", symbols=["process_payment", "validate_card"])
   ```
2. **Add Insights:**
   ```text
   Call: flipchart_add_note(session_id="bug_142", label="Insight", content="validate_card fails if the expiration is the current month", symbols=["validate_card"])
   ```
3. **Generate a Sequence Diagram:**
   ```text
   Call: flipchart_sequence_diagram(symbol="process_payment")
   ```
4. **Render the Board:**
   The agent renders all of this in markdown. The result is a perfect artifact (e.g., `walkthrough.md`) for the user, showing the reasoning process and visual bug schemas.

---

## 🛡️ Recipe 6: Auto-Configuring `.ignore` for Massive Repositories (NEW)

Large monorepos can choke standard indexing tools. Booster MCP v3.0 introduces a Smart Parser.

**Scenario:** You have a Next.js + Python backend monorepo with massive `node_modules` and `venv` folders.
```text
Agent Prompt: Call `add_repo(repo_path="C:\\projects\\massive_monorepo")`
```
*What happens:* Booster automatically detects that this is a new repository and generates a `.ignore` file at the root. It populates it with standard heavy directories (`node_modules`, `venv`, `build`, `target`, `.next`).
It also strictly enforces a traversal depth limit (`MAX_DEPTH = 15`) and utilizes `os.walk` to aggressively prune ignored branches early. 

**Result:** The indexing completes in seconds instead of minutes, and the resulting `repo_map.md` remains clean and highly relevant.

---

## 🎨 Recipe 7: Immersive 3D Rendering with Code City (NEW)

Booster MCP v3.0 brings a Neon/Cyberpunk aesthetic to your repository visualization.

**Scenario:** You want to show the user a visual representation of their code complexity.
```text
Agent Prompt: After running `add_repo`, tell the user: "I have generated a 3D visualization of your repository. Please open `.agents/booster/code_city.html` in your browser."
```
*What the user sees:*
- **Neon Post-Processing:** Files and directories glow with an `UnrealBloomPass` effect against a deep cosmic background `#050510`.
- **Glassmorphism UI:** Floating, semi-transparent menus and legends with backdrop blur overlays.
- **Dynamic Metrics:** Users can dynamically switch the height of the buildings between lines of code (LOC), complexity, and class/function count right from the UI panel.

---

## 🛠 Recipe 8: Developing Custom Agent Skills

You can create your own skills in `.agents/skills/[skill-name]/SKILL.md`.

**Example of an ideal prompt for the `booster-architecture-reviewer` skill**:
```markdown
---
name: booster-architecture-reviewer
description: Project architecture audit using Booster MCP
---

# Instructions

1. Ask the user for the project path and call `add_repo`.
2. Get the structure via `get_repo_map`.
3. Traverse the key modules and call `get_code_city`. Tell the user to view the 3D city to evaluate coupling.
4. Find code duplicates: call `find_duplicates`.
5. Based on the results, generate an `architecture_audit.md` report.
```
When `booster_mcp` starts, these skills are automatically synced into the agent's local directory.

---

## 🎓 Summary: Agent Etiquette Rules

1. **Never read project files blindly (via `find` + `cat` tools).** Always request `get_repo_map()` first.
2. **Use memory.** Discovered a pattern? Save it to `project_memory`.
3. **Be a visionary.** Generate Mermaid diagrams via Flipchart tools—users love visualization.
4. **Don't guess with libraries.** See a new library in `requirements.txt`? Use `fetch_stack_docs` or the Context7 API directly.
