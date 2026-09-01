# Booster MCP API Reference

This document describes the release-facing contracts. The MCP server remains
stdio-first; Booster Home is an optional local HTTP data plane.

## Repository Lifecycle Tools

### `add_repo`

```text
add_repo(repo_path: string, wait: boolean = false) -> object
```

Registers a repository and accepts an indexing job. The legacy `wait` argument is
accepted for compatibility, but the request is nonblocking for both values.
The result includes `job_id`, initial status, repository paths, and artifact
locations.

### `reindex_repo`

Queues a full rebuild using the repository's persisted bounded scan policy. It
returns the job record immediately and does not clear the last ready generation
before a candidate is ready.

### `index_status`

```text
index_status(job_id: string | null = null, repo_path: string | null = null)
```

Returns the job status without waiting for the index state. A job record includes:

- `job_id`, `repository`, `status`;
- `phase`: `scan`, `parse`, `graph`, `embed`, or `finalize`;
- `processed`, `total`, `percent`, `unit`;
- `elapsed_seconds`, `eta_seconds`, `last_progress_at`;
- `generation_id`, `base_generation_id`, `stale`, `stale_reasons`;
- `cancel_requested`, `error`, and snapshot metadata when complete.

Terminal statuses are `completed`, `cancelled`, `failed`, and `superseded`.

### `cancel_index`

```text
cancel_index(job_id: string) -> object
```

Requests cooperative cancellation. The worker stops at a safe directory, file,
or embedding boundary. A currently executing embedding call is not force-killed.
The status may remain `cancelling` briefly before becoming `cancelled`.

### `wait_until_ready`

```text
wait_until_ready(job_id: string, timeout_seconds: float = 30.0) -> object
```

Waits only up to the requested bounded timeout. It returns a terminal job record
or `timed_out=true`; it does not hold the index lock and does not block unrelated
read-only tools.

### Read-only repository tools

`list_repos`, `repo_stats`, `get_repo_artifacts`, `get_repo_map`,
`semantic_search`, and `hybrid_search` use the last ready generation while a
candidate is being built. Their status metadata may include:

```json
{
  "indexing": true,
  "stale": false,
  "generation_id": "...",
  "completeness": {}
}
```

Deleted paths are filtered from search results. A changed source manifest marks a
generation stale and queues a fresh rebuild instead of publishing mixed state.

## Repository Artifacts

All paths are relative to `<repo>/.agents/booster/`:

| Artifact | Contract |
| --- | --- |
| `repo_map_architecture.md` | Bounded macro map with module diversity and mandatory-role coverage |
| `repo_map_symbols.md` | Detailed symbol map with per-file cap |
| `index_health.json` | Generation, coverage, skipped/stale/deleted paths, and timings |
| `repo_map.md` | Compatibility copy of architecture map |
| `code_city.html` | Code City visualization |
| `scan_config.json` | Persisted bounded scanner policy |
| `scan_report.json` | Scanner decisions, inventory, skips, and manifest |
| `snapshots/` | Immutable artifact history keyed by git/artifact state |

## Booster Home HTTP API

Home binds to loopback by default. Loopback requests do not require a gateway
token. A non-loopback bind requires `home.auth_token` with at least 16 characters
and `Authorization: Bearer <token>` on every gateway endpoint.

### Health and status

```text
GET /health
GET /booster/status
GET /v1/models
```

`/health` reports configuration readiness without exposing credentials. `/v1/models`
proxies upstream model discovery and falls back to the configured model when the
upstream list is unavailable.

### Chat Completions

```text
POST /v1/chat/completions
```

The request is compiled, session-scoped, and forwarded to an OpenAI-compatible
upstream. `stream=true` returns SSE chunks without whole-response buffering.
Unknown/provider-specific response fields are preserved.

### Responses

```text
POST /v1/responses
```

Home supports Responses input/output and provides an explicit Chat Completions
fallback for upstreams that return HTTP 404 for Responses. A failed fallback is
reported as an upstream error rather than a fabricated response.

### Nemotron note

Nemotron deployments may place generated reasoning in `reasoning_content` and
return empty `message.content` when the output budget ends during reasoning.
Home preserves this provider-specific field. Clients should check
`finish_reason`, usage, and both content fields before treating a response as
complete.

## Context and Memory Invariants

- system and active user context are protected by the compiler policy;
- raw blocks are persisted before eviction;
- artifact content is hash-verified on write and read;
- session artifact references are isolated by session ID;
- known hard-budget violations fail closed;
- binary checkpoints are metadata-only and are never read into model context;
- API keys and auth tokens are redacted from logs, telemetry, status, and errors.

## Booster Observatory Read-only API

The Observatory gateway is same-origin and accepts logical `repo_id` values from
its allowlist. It never accepts a repository root path from the browser.

```text
GET  /api/v1/status
POST /api/v1/architecture
POST /api/v1/search
POST /api/v1/symbol/focus
POST /api/v1/impact
POST /api/v1/history
POST /api/v1/diagnostics
POST /api/v1/related-tests
GET  /api/v1/snapshots
POST /api/v1/snapshots/compare
GET  /api/v1/city
GET  /api/v1/city/html
```

`GET /api/v1/city` returns normalized `buildings`, `connections`, `districts`,
and `metrics` data. `GET /api/v1/city/html` serves the interactive Code City
artifact.

Operation responses use `{ok, request_id, repo, result, ui, meta}`. Errors are
normalized to `REPO_NOT_FOUND`, `SYMBOL_NOT_FOUND`, `FILE_NOT_FOUND`,
`SNAPSHOT_NOT_FOUND`, `INDEX_NOT_READY`, `INVALID_ARGUMENT`, `RATE_LIMITED`,
`TIMEOUT`, or `INTERNAL_ERROR`; tracebacks are never returned.

The gateway applies four concurrent analysis slots, a ten-second deadline, and a
per-client sliding-window rate limit. Search, impact, history, and snapshot
comparison results are cached only under the current `(repo_id, generation_id,
operation, normalized_args)` key. A generation change invalidates stale browser
state and causes Code City to reload.

## Demo Build

```bash
booster web prepare-demo --project .
booster web --mode demo --project .
```

`prepare-demo` may perform the expensive build-time indexing, history collection,
and snapshot materialization from real repository evidence. Demo startup loads
the prepared state into the existing indexer, consumes prepared diagnostics and
history, and does not reindex, invoke Git, or download an embedding model.
Browser-facing demo actions remain read-only.
