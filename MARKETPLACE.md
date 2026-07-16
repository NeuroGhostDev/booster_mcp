# Booster MCP Marketplace and Distribution Guide

Booster MCP is compatible with MCP clients and popular catalogs such as
Smithery, Glama, VS Code, and Claude Desktop.

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

- Document every tool with clear arguments and descriptions.
- Keep working examples and regression workflows in [COOKBOOK.md](COOKBOOK.md).
- Publish versioned GitHub Releases.
- Declare every runtime dependency in [pyproject.toml](pyproject.toml).
- Validate the release with `uv lock --check`, `pytest`, and Ruff.
