# Booster MCP Architecture

## System Boundary

Booster is an AI-platform and developer-tooling project with two runtime planes:

```text
Coding agent / MCP client
            |
            v
     MCP control plane
     - repository index
     - symbols and graphs
     - search and Code City
     - project memory
     - diagnostics and validation
            |
            +--------------------+
            |                    |
            v                    v
      Booster Home         Local or remote model
      - context compiler   - LM Studio
      - session memory     - vLLM
      - artifact store     - Ollama
      - research tools     - other OpenAI-compatible backends
      - gateway
```

The control plane and Home data plane share the existing `RepoIndexer` and
`CognitiveRuntime`. Home must not create a second repository index, vector
database, or parallel gateway.

## Source Boundaries

| Area | Location | Responsibility |
| --- | --- | --- |
| MCP entrypoint | `server.py` | FastMCP server construction and tool registration |
| CLI | `cli.py` | Repository control, Home inspection, and launcher commands |
| Repository intelligence | `indexer.py`, `repository_scanner.py`, `parser_router.py`, `chunker.py` | Bounded scanning, parsing, chunks, and index lifecycle |
| Index lifecycle | `indexing_jobs.py`, `repository_lifecycle.py` | Observable jobs, cancellation, stale generations, and immutable snapshots |
| Graph and retrieval | `graphs.py`, `vector_index.py`, `repomap.py` | Calls/imports, semantic search, lexical search, and Repo Map |
| Cognitive Runtime | `cognitive_runtime.py`, `context_provider.py`, `toolkit.py` | Impact analysis, memory, diagnostics, and validation loops |
| Visualizer | `visualizer.py`, `city_server.py`, `watcher.py` | Code City artifacts and live regeneration |
| Skills | `skills/` | Bundled agent workflows installed by `skill_installer.py` |
| Home runtime | `booster_home/` | Gateway, context compiler, persistence, workers, telemetry, and research tools |
| Documentation | `README.md`, `CONTRIBUTING.md`, `docs/`, `RECOMENDET_PROMPT.md` | User, maintainer, architecture, and agent guidance |

The top-level control-plane module names are kept stable for compatibility with
the installed entrypoints and existing integrations. A future package-layout
migration should add compatibility shims and update packaging in one dedicated
change.

## Request Flow

### MCP Request

```text
client request
  -> FastMCP tool
  -> job/status boundary
  -> ready repository generation
  -> bounded result
```

### Repository Index Job

```text
add_repo / reindex_repo
  -> IndexJobManager
  -> scan -> parse -> graph -> embed -> finalize
  -> candidate generation
  -> manifest stability check
  -> atomic ready-generation promotion
  -> architecture map + symbol map + index health + snapshot
```

The candidate generation is built outside the ready-state pointer swap. During a
long scan or embedding phase, read-only tools return the last ready generation
with `indexing`, `stale`, `generation_id`, and completeness metadata. A cancelled
or unstable candidate never replaces the last ready generation.

### Home Inference Request

```text
OpenAI-compatible request
  -> session resolution
  -> context classification
  -> deterministic normalization
  -> persist-before-evict artifact store
  -> budget allocation and optional retrieval
  -> protected message packing
  -> upstream model
```

Compression is not data loss. Any evicted raw block must be persisted and hash
verified before the request can continue. A known hard-budget violation fails
closed.

## Generated Artifacts

Generated repository artifacts belong under the project-local
`.agents/booster/` directory and must not be confused with source files:

- `repo_map.md`;
- `repo_map_architecture.md`;
- `repo_map_symbols.md`;
- `index_health.json`;
- `code_city.html`;
- `scan_config.json`;
- `scan_report.json`;
- immutable snapshots under `snapshots/`;
- runtime sessions and compressed raw artifacts.

`repo_map_architecture.md` is the bounded context-facing macro map. It reserves
coverage for top-level modules and architectural roles such as entrypoints,
configs, contracts, and control-plane registrations. `repo_map_symbols.md` is
more detailed but still applies a per-file cap. `repo_map.md` remains a
backward-compatible copy of the architecture map.

Large model and checkpoint bodies are never loaded into the coding-agent
context. Research tools expose checkpoint metadata and sidecar evidence only.

## Testing Boundaries

- `tests/` contains the maintained automated regression suite.
- `tests/home/` covers the Home runtime, gateway, workers, memory, and research
  coprocessor.
- `benchmarks/` contains reproducible performance and context-budget workloads.
- Generated HTML, logs, caches, and build output are not test fixtures.
- `tests/test_index_jobs.py`, `tests/test_server_index_jobs.py`, and
  `tests/test_repomap.py` cover job lifecycle, nonblocking reads, and large-module
  map diversity.
