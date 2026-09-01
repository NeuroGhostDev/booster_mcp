# Booster MCP Cookbook

Welcome to the **Booster MCP Cookbook**. This guide contains verified recipes for
Booster MCP 4.0: repository intelligence, Context Injection, Cognitive Runtime,
job-based indexing, and Booster Home.

Booster MCP transforms your AI agent into a "Senior Engineer" capable of quickly understanding architecture, finding deep context, building 3D visualizations, integrating up-to-date library documentation (Context7), and running a Cognitive Runtime loop before and after code changes.

---

## 📖 Recipe 1: Instant Onboarding in a New Project

When an agent first encounters a large project, it doesn't need to read hundreds of files blindly. It needs a "map of the territory" and a view of the "city."

**Step 1. Add Repository to the Index**

```text
Agent Prompt: Call the `add_repo` tool with the absolute path to the project.
Example: add_repo(repo_path="C:\\projects\\my_large_app")
Then call repo_stats() to check indexing progress.
```

_What happens:_ Booster registers the repository and starts a background job, so a
long scan cannot block the MCP stdio request. When indexing completes, Booster
has code symbols, call and import graphs, and generated artifacts under
`.agents/booster/`: `repo_map_architecture.md`, `repo_map_symbols.md`,
`index_health.json`, `code_city.html`, and the compatibility `repo_map.md`. It
also auto-generates a `.ignore` file to skip noisy directories such as
`node_modules` and `venv`. The old `wait=true` argument remains accepted but is
non-blocking; use the job tools below for lifecycle control.

Check the job explicitly:

```text
index_status(repo_path="C:\\projects\\my_large_app")
wait_until_ready(job_id="idx_...", timeout_seconds=30)
cancel_index(job_id="idx_...")
```

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

Use semantic search, hybrid retrieval, and AST analysis instead of blind `grep`.

**Scenario:** You need to find where user authentication occurs in the project.

```text
Agent Prompt: Call `semantic_search(query="user authentication logic JWT")`
```

Booster will find relevant code snippets by _meaning_, even if the exact string "JWT" is missing from the code.

**Scenario:** You know part of an API name, class name, or `snake_case` symbol and also want semantic context.

```text
Agent Prompt: Call `hybrid_search(query="validate_access_token", k=5)`
```

`hybrid_search` combines normalized dense cosine similarity with BM25 lexical retrieval and fuses both rankings. It is especially effective for identifiers such as `validateAccessToken`, file names, framework APIs, and mixed natural-language queries.

**Scenario:** The function `verify_token` was found. You need to see who calls it and what it calls.

```text
Agent Prompt: Call `flipchart_call_graph(symbol="verify_token", max_depth=3)`
```

Booster returns a Mermaid call graph diagram. The agent renders it, and the developer instantly understands the authorization flow.

---

## 🧠 Recipe 3: Cognitive Runtime Preflight Before a Code Change

Use this recipe when the agent is about to edit shared code, refactor a symbol,
or fix a bug in a non-trivial path.

**Problem:** A normal coding agent often jumps from a user request to a patch.
That skips the things a human engineer checks first: blast radius, git history,
project rules, diagnostics, and tests.

**Goal:** Make the agent inspect the system before it writes code.

```text
Agent Prompt:
Call `preflight_analysis` before editing.

preflight_analysis(
   task="Refactor AuthService token validation",
   target="AuthService",
   paths=["src/auth/service.py"],
   repo="C:\\projects\\my_app"
)
```

_What happens:_ Booster gathers project memory, runs impact analysis, checks
the affected files for diagnostics, and returns a recommended engineering
order.

For deeper context, ask the agent to call the lower-level tools explicitly:

```text
project_memory_recall(query="auth token validation", repo="C:\\projects\\my_app")
impact_analysis(target="AuthService", repo="C:\\projects\\my_app", max_depth=3)
git_intelligence(symbol="AuthService", repo="C:\\projects\\my_app", limit=8)
collect_diagnostics(paths=["src/auth/service.py"], repo="C:\\projects\\my_app")
```

**Result:** The agent can explain:

- which symbols and files are affected;
- which calls are internal and which are unresolved external calls;
- which tests are likely relevant;
- what git history says about the target;
- what project facts should constrain the patch;
- what diagnostics already fail before the change.

---

## ✅ Recipe 4: Validate and Repair After a Patch

Use this recipe after the agent has modified files.

```text
run_validation_checks(
   paths=["src/auth/service.py"],
   commands=["pytest tests/auth -q"],
   repo="C:\\projects\\my_app"
)
```

_What happens:_ Booster collects diagnostics and runs the focused validation
command. Diagnostics are fail-closed: if Ruff, Pyright, TypeScript, Rust,
Bandit, Semgrep, or another configured tool crashes or times out, Booster
reports an error finding instead of pretending validation passed.

**Repair loop for the agent:**

```text
1. Read the first diagnostic or failing command.
2. Repair the same touched slice.
3. Run `run_validation_checks` again.
4. Stop when validation passes or the failure disproves the current hypothesis.
```

**Result:** The agent behaves less like a patch generator and more like an
engineer running a focused red/green loop.

---

## 🧠 Recipe 5: Context Injection

Booster provides **Active Context** so agents can gather project knowledge and keep core ideas available across restarts.

**Working with Project Memory (`project_memory`):**
When an agent makes an important architectural decision (e.g., "In this project, we use Pydantic v2 and dependency injection"), it should record it:

```text
Agent Prompt: Call `project_memory(action="set", key="architecture_rules", value="Use Pydantic v2 and DI container. No singletons.")`
```

On the next run, the `booster-onboard` skill automatically pulls these rules and injects them into the agent's system prompt.

---

## 📚 Recipe 6: Working with Context7 (Fresh External Docs)

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

## 📊 Recipe 7: Debugging Sessions with Flipchart

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

## 🛡️ Recipe 8: Bounded Scanning for Massive Repositories (NEW)

Large monorepos can overwhelm unbounded indexing. Start with the Booster CLI to create a reusable scan policy before connecting the project to an MCP client.

**Scenario:** You have a Next.js + Python backend monorepo with massive `node_modules` and `venv` folders.

```text
Terminal: cd C:\projects\massive_monorepo && booster expand --profile balanced
```

_What happens:_ Booster stores `.agents/booster/scan_config.json`, then creates
the architecture map, symbol map, `index_health.json`, compatibility
`repo_map.md`, and `scan_report.json`. The shared scanner prioritizes source
roots, prunes generated and dependency directories early, and applies limits for
depth, directories, file count, individual file size, and total selected bytes.
It continues a bounded metadata inventory beyond the selected-file cap so
changes outside the body budget can mark a generation stale. `add_repo()` uses
the same policy and `reindex_repo()` queues an explicit rebuild.

At the end of the agent task, call `booster.task_complete(task_id="task-123")`.
Booster queues one final bounded reindex and stores the generated artifacts in
an immutable snapshot keyed by the current git commit and artifact digest.
Earlier snapshots remain available under `.agents/booster/snapshots/`.

**Result:** The first map is available quickly, the selected scope is explainable from `scan_report.json`, and agents can request `--profile deep` only when the task genuinely needs broader coverage.

---

## Release Recipe: Run Booster Home with Nemotron 4B

Use Booster Home as a local OpenAI-compatible data plane in front of LM Studio.
The model ID must match the ID reported by `/v1/models`.

```bash
booster home \
  --base-url http://127.0.0.1:1234/v1 \
  --model nvidia/nemotron-3-nano-4b \
  --api-key lm-studio \
  --project .
```

Check the configuration without starting a second gateway:

```bash
booster home --base-url http://127.0.0.1:1234/v1 \
  --model nvidia/nemotron-3-nano-4b --api-key lm-studio \
  --probe-generation doctor --json
```

Home preserves provider-specific fields such as `reasoning_content`. Nemotron
may consume a small output budget in reasoning and return an empty
`message.content` with `finish_reason=length`; increase the output budget or
inspect the reasoning field instead of treating that response as a complete
answer.

Smoke-test the three public request paths:

```text
GET  /health
GET  /v1/models
POST /v1/chat/completions
POST /v1/responses
```

For streaming, measure time to the first SSE chunk separately from total
completion time. Home forwards chunks instead of buffering the entire upstream
response.

---

## Release Recipe: Context Injection Before a Change

Use the existing Booster world model before reading a large repository manually:

```text
add_repo(repo_path="C:\\projects\\my_app")
index_status(repo_path="C:\\projects\\my_app")
inject_context(
    include_map=true,
    include_stack=true,
    include_conventions=true
)
```

Then run a focused preflight:

```text
preflight_analysis(
    task="Change the authentication flow",
    target="AuthService",
    paths=["src/auth/service.py"],
    repo="C:\\projects\\my_app"
)
```

The injected slice should contain the architecture map, stack, project
conventions, relevant diagnostics, and impact evidence. Use `artifact_lookup` or
`retrieve_session_artifact` when exact evicted content is needed; do not replace
an exact artifact with a model-generated reconstruction.

---

## 🔌 Recipe 9: Connect and Control Booster After Installation (NEW)

The Windows, Linux, and macOS installers create a `booster` launcher in the user's local bin directory. Open a new terminal, change into the repository you want to manage, and run:

```text
booster control
```

The interactive menu can connect a VS Code workspace, a VS Code user profile, or Claude Desktop. It can also inspect the selected runtime, change the persisted bounded scan policy, refresh artifacts, run a dependency doctor, disconnect one server entry, and update the launcher.

Use a workspace entry when the server belongs to one repository. It writes `.vscode/mcp.json` and starts with that repository in `REPOS`:

```text
booster control connect --client vscode --scope workspace --project .
booster expand --profile balanced
```

Use a user entry when Booster should be visible in every VS Code workspace. The global entry starts without `REPOS`; after it starts, the agent should call `add_repo` for the project currently being worked on:

```text
booster control connect --client vscode --scope user --project .
```

For scripts, CI, and support workflows, use non-interactive commands:

```text
# Inspect the exact Python, MCP config, scan policy, and generated artifacts.
booster control status --client vscode --scope workspace --project .

# Save a broader policy before reindexing a large repository.
booster control scan --project . --profile deep --max-files 2000

# Check that the installed environment contains FastMCP, FAISS, BM25, and embeddings.
booster control doctor --project .

# Remove only Booster's named entry from a client config.
booster control disconnect --client vscode --scope workspace --project .
```

`connect` generates a stdio entry using the exact Python environment that installed Booster. This prevents accidental fallback to an unrelated system Python. Every changed client config is written atomically and its previous version is saved beside it with the `.booster.bak` suffix. Existing servers and client-specific settings are preserved.

---

## 🛑 Recipe 10: Debug a Stop-Criterion Narrative Regression (NEW)

**Scenario:** A critical stop atom correctly sets an evaluation stage score to zero and preserves the visible stop label, but the report suddenly contains the same three generic narrative paragraphs for every dialog. Prompt changes have no effect.

This is a control-flow problem, not a prompt-writing problem. The likely defect is a stop branch that bypasses the writer LLM or overwrites its `strengths`, `weaknesses`, and `recommendations` after generation.

1. Connect the target repository through `booster control` or call `add_repo`.
2. Inspect `get_repo_map` and `get_repo_artifacts` before opening many files.
3. Search for the branch and its fallback text:

   ```text
   semantic_search(query="is_stage_stop narrative_context writer hardcoded report fallback")
   hybrid_search(query="is_stage_stop strengths weaknesses recommendations", k=8)
   ```

4. Locate the report builder and writer invocation with `find_symbol`, then generate a sequence view:

   ```text
   flipchart_sequence_diagram(symbol="build_stage_report")
   ```

5. Keep the scoring rule intact, but ensure that the stop branch passes the original `stage.narrative_context` to the writer and does not replace its three narrative fields with fixed text.
6. Add a regression test with a triggered stop atom. Verify all of the following:
   - stage points remain zero;
   - the stop label remains visible;
   - atom-level zeroing remains intact;
   - the writer receives the stop-aware narrative context;
   - the generated narrative includes the trigger and a concrete corrective recommendation.

**Result:** Critical errors still enforce the score rule, while the report remains specific, pedagogical, and grounded in the evaluated dialog.

---

## 🎨 Recipe 11: Immersive 3D Rendering with Code City (NEW)

Booster MCP includes a Neon/Cyberpunk aesthetic for repository visualization.

**Scenario:** You want to show the user a visual representation of their code complexity.

```text
Agent Prompt: After running `add_repo`, tell the user: "I have generated a 3D visualization of your repository. Please open `.agents/booster/code_city.html` in your browser."
```

_What the user sees:_

- **Neon Post-Processing:** Files and directories glow with an `UnrealBloomPass` effect against a deep cosmic background `#050510`.
- **Glassmorphism UI:** Floating, semi-transparent menus and legends with backdrop blur overlays.
- **Dynamic Metrics:** Users can dynamically switch the height of the buildings between lines of code (LOC), complexity, and class/function count right from the UI panel.

---

## 🛠 Recipe 12: Developing Custom Agent Skills

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

## Recipe 13: Prepare a WebMCP Demo Bundle

Prepare the demo once from the repository root. Indexing and embedding work are
build-time operations; the resulting demo process loads the same `RepoIndexer`
state and does not repeat them on the first HTTP request.

```bash
booster web prepare-demo --project .
booster web --mode demo --project .
```

For container deployment:

```bash
docker build -f Dockerfile.observatory -t booster-observatory .
docker run --rm -p 8000:8000 booster-observatory
```

Open `http://127.0.0.1:8000/`. The bundle contains `manifest.json`, `city.json`,
`architecture.json`, `diagnostics.json`, `history.json`, `snapshots.json`,
`code_city.html`, and portable JSON+FAISS index state. History and snapshot
comparison data are prepared from real repository evidence, and the browser
runtime is read-only.

## Recipe 14: Run the Observatory Agent Workflow

Use the native WebMCP tools in this order when explaining a repository change:

```text
booster_search_code(query="repository indexing")
booster_focus_symbol(symbol="RepoIndexer.full_index")
booster_trace_impact(target="RepoIndexer.full_index", max_depth=3)
booster_find_related_tests(target="RepoIndexer.full_index")
```

The result is visible in one page: matching buildings highlight, the target is
focused, the impact panel shows callers/callees/tests, and Agent Activity records
the action. A human can click another building; the page then registers
`booster_analyze_selected_file` and `booster_history_of_selected_file` for that
selection.

## Recipe 15: Inspect Evidence and Snapshots

History, diagnostics, architecture, and snapshots are read-only actions over
existing Booster artifacts and runtime capabilities:

```text
booster_explain_history(path="cognitive_runtime.py")
booster_show_diagnostics(paths=["cognitive_runtime.py"])
booster_inspect_architecture(focus="cognitive_runtime.py")
booster_compare_snapshots(from="snapshot-a", to="snapshot-b")
```

Snapshot comparison uses immutable snapshot IDs and classifies files as added,
removed, changed, or stable. It never accepts an arbitrary snapshot filesystem
path from the browser.

## Recipe 16: Verify the Public Boundary

Run automated checks before publishing:

```bash
uv run pytest -q
uv run pytest tests/webmcp/browser/test_browser.py -q
node --experimental-default-type=module --test tests/webmcp/browser/webmcp_modules.test.mjs
uv run ruff check .
uv build --wheel
uv sync --locked --extra security
uv run bandit -r booster_web indexer.py vector_index.py repository_lifecycle.py watcher.py city_server.py -q
```

The gateway is same-origin and read-only. It allowlists logical repository IDs,
checks repository containment, limits analysis concurrency to four operations,
times out operations after ten seconds, and applies a per-client rate limit. It
does not expose shell commands, validation commands, mutation, cloning, or
arbitrary processes. Finally open the URL in ChatGPT's in-app browser and Chrome
with WebMCP enabled; fake `document.modelContext` tests are not a replacement
for that real-browser check.

The `Share state` control preserves only safe `repo_id`, relative file, mode, and
snapshot IDs in the URL. It is suitable for reproducing a view without leaking a
local repository root.

---

## 🎓 Summary: Agent Etiquette Rules

1. **Never read project files blindly (via `find` + `cat` tools).** Always request `get_repo_map()` first.
2. **Use memory.** Discovered a pattern? Save it to `project_memory`.
3. **Be a visionary.** Generate Mermaid diagrams via Flipchart tools—users love visualization.
4. **Don't guess with libraries.** See a new library in `requirements.txt`? Use `fetch_stack_docs` or the Context7 API directly.
