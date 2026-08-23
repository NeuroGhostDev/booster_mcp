# Booster MCP Release Procedure

This procedure prepares a source release and wheel without publishing local
repository data.

## 1. Scope and Version

1. Confirm the intended version in `pyproject.toml`.
2. Update the top section of `CHANGELOG.md` with the release date and verified
   behavior.
3. Keep `README.md` as the canonical English reference and synchronize
   `README.ru.md` and `README.zh-CN.md`.
4. Update `docs/API.md`, `docs/ARCHITECTURE.md`, `COOKBOOK.md`, and
   `MARKETPLACE.md` for public contract changes.

## 2. Repository Hygiene

Check for accidental release inputs:

```powershell
git status --short
git diff --check
```

Do not include:

- `.venv`, `build`, `dist`, caches, logs, or test output;
- `.agents/booster/runtime/` and local session artifacts;
- repository registries, API keys, auth tokens, or private paths;
- generated `code_city.html` and repository maps from a developer workspace;
- binary model or checkpoint bodies.

Customer-facing evidence under `algocheck/` may be published only after
reviewing every screenshot for private account data, local paths, tokens, and
unrelated application content. Keep the case study explicit about what was
observed and do not present it as a controlled benchmark unless the evaluation
was run with fixed conditions.

## 3. Validation Gate

Run from a clean dependency environment:

```bash
uv sync --locked --extra dev
uv lock --check
uv run ruff check .
uv run python -m pytest tests -q
uv run python -m compileall -q booster_home indexing_jobs.py server.py
uv build
```

If formatting is part of the changed slice, also run:

```bash
uv run black --check visualizer.py tests/test_visualizer.py \
  booster_home/research tests/home/test_research.py
```

## 4. Runtime Smoke

For a local OpenAI-compatible backend:

```bash
booster home \
  --base-url http://127.0.0.1:1234/v1 \
  --model nvidia/nemotron-3-nano-4b \
  --api-key lm-studio \
  --project .
```

Verify:

1. `GET /health` returns `200` without leaking credentials.
2. `GET /v1/models` includes the configured or discovered model.
3. Chat Completions non-stream returns `200` and preserves provider fields.
4. Chat Completions stream delivers a first SSE chunk before completion.
5. `/v1/responses` returns a native response or an explicit compatibility
   fallback.
6. `booster home --probe-generation doctor --json` reports `ok=true`.
7. Nemotron responses are checked for `reasoning_content`, `message.content`,
   usage, and `finish_reason`.

For repository intelligence, use a disposable fixture to verify:

1. `add_repo(wait=true)` returns immediately with `job_id`.
2. `index_status` exposes phase, progress, ETA, and generation metadata.
3. `cancel_index` reaches a terminal `cancelled` state.
4. `list_repos` and `get_repo_artifacts` remain responsive during a slow build.
5. A synthetic monorepo keeps giant modules, frontend, control-plane,
   entrypoints, and contracts represented in the architecture map.
6. A changed or deleted path marks the generation stale and is absent from
   semantic search results.

## 5. Package Inspection

Inspect the built artifacts:

```bash
python -m zipfile -l dist/booster_mcp-*.whl
```

The wheel must contain `booster_home/`, `indexing_jobs.py`, the stable root
modules, bundled skills, and package metadata. It must not contain local session
data, credentials, generated repository artifacts, or `.venv` files.

## 6. Publish

After the validation gate passes:

1. Create a Git tag matching the package version.
2. Publish the GitHub Release using `CHANGELOG.md` as the release body.
3. Attach the source distribution and wheel produced by `uv build`.
4. Update marketplace listings only after the public release URL exists.
5. Keep the release smoke output and package file list as maintainer evidence.

No release is complete when tests pass but the wheel, runtime smoke, security
defaults, or documentation are unverified.
