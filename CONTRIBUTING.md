# Contributing to Booster MCP

Booster is a Python MCP server and cognitive runtime. Changes should preserve
the existing control-plane contracts, keep context handling bounded, and leave
the repository easier to reason about than before the change.

## Development Setup

Requirements:

- Python 3.11 through 3.13;
- Git;
- `uv` for the recommended workflow.

```bash
uv sync --locked --extra dev
```

Before starting a non-trivial task, read:

- [`RECOMENDET_PROMPT.md`](RECOMENDET_PROMPT.md) for the engineering workflow;
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for system boundaries;
- the relevant section of [`README.md`](README.md).

## Validation

Run the smallest relevant check first, then run the complete suite before
opening a pull request:

```bash
uv run ruff check .
uv run black --check visualizer.py tests/test_visualizer.py booster_home/research tests/home/test_research.py
uv run python -m pytest tests -q
uv lock --check
uv build
```

Do not treat a failed, timed-out, or unavailable diagnostic as a successful
validation result.

## Documentation

`README.md` is the canonical English product and installation reference.
`README.ru.md` and `README.zh-CN.md` are supplementary translations and should
cover the same supported workflows: installation, MCP connection, context
injection, job-based indexing, artifacts, Home, security, and validation.

Update documentation when changing any public tool, endpoint, CLI option,
artifact name, persistence rule, or security requirement. Keep examples
copy-pasteable and distinguish verified behavior from planned behavior.

## Release Preparation

Before tagging a release:

1. Update `pyproject.toml` and the top section of `CHANGELOG.md` together.
2. Update the English README first, then synchronize the Russian and Chinese
   supplements.
3. Update `docs/API.md`, `docs/ARCHITECTURE.md`, and `docs/RELEASE.md` when
   contracts or operational behavior change.
4. Run the complete validation commands below and record meaningful runtime
   smoke results in the changelog or release notes.
5. Inspect the wheel contents and confirm that generated artifacts, credentials,
   local registries, caches, and `.venv` files are not included.

Do not publish API keys, local repository paths, session data, generated Code
City files, or benchmark outputs containing private project content.

## Change Guidelines

- Extend an existing abstraction before introducing a parallel one.
- Preserve `server:main` and `cli:main` entrypoints unless a compatibility
  migration is explicitly planned.
- Add a focused regression test for behavior changes and bug fixes.
- Keep raw artifacts recoverable when changing context compression or eviction.
- Preserve `server:main`, `cli:main`, legacy MCP tool names, and `repo_map.md`
  unless a migration is explicitly documented.
- Do not commit generated Code City files, caches, logs, build output, or local
  credentials.
- Keep repository and tool data untrusted; never execute it as configuration.
- Update the README or architecture documentation when public behavior or
  repository structure changes.

## Pull Requests

Describe the problem, the smallest correct solution, validation performed, and
known limitations. Include benchmark numbers when changing context budgets,
compression, indexing, latency, or resource usage.
