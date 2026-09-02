# Booster MCP Marketplace and Distribution Guide

Booster MCP 4.0 is a Cognitive Runtime for coding agents. It builds a local
world model of a repository: architecture and symbol maps, hybrid search, AST
impact graph, git history, project memory, diagnostics, validation loops, and an
optional OpenAI-compatible Booster Home gateway.

Use this document when publishing Booster to MCP catalogs such as Smithery,
Glama, VS Code, Claude Desktop, and community lists.

## Product Positioning

### One-line pitch

Booster gives AI coding agents the perception layer they miss: architecture,
history, diagnostics, memory, and validation before they edit code.

### Short catalog description

Booster MCP turns a repository into a live software world model for coding
agents. It combines bounded scanning, repo maps, semantic and lexical search,
Tree-sitter call/import graphs, git history/blame, long-term project memory,
fail-closed diagnostics, and validation loops. Use it when you want Cursor,
Claude Code, VS Code agents, or other MCP clients to understand a codebase
before generating patches.

### Longer catalog description

Most coding agents can generate code, but they often edit with weak context:
they grep a few files, miss architecture, ignore existing diagnostics, forget
project rules, and stop before validation. Booster MCP adds the missing runtime
between the agent and the repository. It builds compact repo maps, tracks
symbols and call/import relationships, recalls project facts, checks git
history, collects compiler/linter/security diagnostics, and guides the agent
through Plan -> Implement -> Validate -> Repair.

### Tagline options

- Cognitive Runtime for coding agents.
- A live world model of your software system.
- IDE perception, git memory, and validation loops for AI agents.
- Stop giving agents random files. Give them the system map.

### Problems solved

- Agents waste context reading unrelated files.
- Semantic search returns snippets, not architecture.
- Refactors happen without blast-radius analysis.
- Historical code intent is hidden in git history.
- Project-specific rules disappear between sessions.
- Type/lint/security diagnostics are ignored until late.
- Patches are produced without a repeatable validation loop.

### Differentiators

- Local-first MCP server; no hosted code upload is required.
- Bounded scanning keeps large repositories predictable.
- Hybrid retrieval combines FAISS semantic search and BM25 lexical search.
- Cognitive Runtime adds impact analysis, git intelligence, project memory,
  diagnostics, and validation tools.
- Diagnostics are fail-closed: broken tools become error findings, not false
  success.
- Bundled skills teach agents how to onboard, debug, add features, refactor,
  review, and use Cognitive Runtime.
- Booster Home compiles context, preserves evicted raw artifacts, forwards SSE,
  and supports local OpenAI-compatible backends such as LM Studio and vLLM.
- Nemotron-specific `reasoning_content` is preserved instead of being silently
  discarded when ordinary message content is empty.

## Recommended Listing Metadata

```yaml
name: Booster MCP
category: Developer Tools
tags:
  - mcp
  - coding-agents
  - code-intelligence
  - semantic-search
  - repo-map
  - diagnostics
  - context-runtime
  - openai-compatible
  - ai-engineering
  - developer-productivity
version: 4.1.4
license: MIT
repository: https://github.com/NeuroGhostDev/Booster-mcp
runtime:
  python: ">=3.11,<3.14"
  entrypoint: booster
```

Use the packaged installation and `booster control` for local client setup.
The command writes the correct absolute Python and `server.py` paths for the
current platform instead of relying on a system interpreter.

## 1. Publish to Smithery

[Smithery](https://smithery.ai) allows one-command MCP server installation.

Ensure the project has a valid `smithery.yaml` manifest in the repository root,
or configure the Smithery CLI to generate one.

Add a badge to [README.md](README.md) when the public server ID is available:

```markdown
[![smithery badge](https://smithery.ai/badge/booster-mcp)](https://smithery.ai/server/booster-mcp)
```

Offer the client installation command when applicable:

```bash
npx -y @smithery/cli install booster-mcp --client claude
```

## 2. Publish to Glama

[Glama](https://glama.ai) is a catalog for MCP servers and agents.

To publish:

1. Sign in to `glama.ai/mcp`.
2. Add the GitHub repository URL.
3. Let Glama parse the current README and server metadata.

Add the Glama badge after the server ID is assigned:

```markdown
<a href="https://glama.ai/mcp/servers/n6l9tqkh8f"><img width="380" height="200" src="https://glama.ai/mcp/servers/n6l9tqkh8f/badge" alt="Booster MCP Server badge" /></a>
```

Replace the placeholder ID with the ID assigned by Glama.

## 3. Configure Local Clients

Do not copy a generic `python` command into a client configuration. Use the
installed control command so the client starts the verified Booster environment:

```text
# Available in every VS Code workspace. Add repositories through add_repo.
booster control connect --client vscode --scope user --project .

# Preferred for a project-owned .vscode/mcp.json.
booster control connect --client vscode --scope workspace --project .

# Claude Desktop user profile.
booster control connect --client claude --scope user --project .
```

`booster control` creates an atomic backup with the `.booster.bak` suffix
before changing a client configuration. Run `booster control doctor --project .`
before publishing installation instructions.

## 4. Release Checklist

- Lead with the pain: agents edit code without architecture, memory,
  diagnostics, or validation.
- Show the Cognitive Runtime workflow in [README.md](README.md).
- Keep working examples and regression workflows in [COOKBOOK.md](COOKBOOK.md).
- Document every MCP tool with clear arguments and descriptions.
- Document `index_status`, `cancel_index`, and `wait_until_ready`; do not describe
  `add_repo(wait=true)` as a blocking operation.
- List the split repository artifacts: `repo_map_architecture.md`,
  `repo_map_symbols.md`, `index_health.json`, and compatibility `repo_map.md`.
- Verify the Home gateway against the selected OpenAI-compatible backend. For
  Nemotron, check both `message.content` and `reasoning_content`.
- Publish versioned GitHub Releases with screenshots or CLI output examples.
- Declare every runtime dependency in [pyproject.toml](pyproject.toml).
- Validate the release with `uv lock --check`, `uv run python -m pytest tests -q`,
  `uv run ruff check .`, and `uv build`.
- Inspect wheel contents for credentials, local paths, caches, generated
  artifacts, and session data.

See [docs/RELEASE.md](docs/RELEASE.md) for the maintainer release procedure and
[docs/API.md](docs/API.md) for the public MCP and Home contracts.

## 5. Suggested Social / Launch Copy

```text
Most AI coding agents can write patches. The hard part is giving them the
software system around the patch.

Booster MCP builds a local world model for agents: repo map, hybrid search,
AST impact graph, git history, project memory, diagnostics, and validation
loops.

It is not another grep wrapper. It is a Cognitive Runtime for coding agents.
```

```text
Before editing code, an agent should know:

- what calls this symbol;
- which files and tests are affected;
- why the code exists in git history;
- what project rules must be remembered;
- what type/lint/security diagnostics already fail;
- which validation command to run after the patch.

That is what Booster MCP gives it.
```
