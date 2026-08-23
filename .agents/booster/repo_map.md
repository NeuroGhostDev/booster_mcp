# Booster Repo Map

## Coverage

- candidate_files: 150
- selected_files: 125
- candidate_modules: ['.', 'algocheck', 'assets', 'benchmarks', 'booster_home', 'docs', 'skills', 'tests']
- represented_modules: ['.', 'algocheck', 'assets', 'benchmarks', 'booster_home', 'docs', 'skills', 'tests']
- omitted_modules: []
- mandatory_roles_found: ['config', 'contract', 'control', 'entrypoint']
- mandatory_roles_selected: ['config', 'contract', 'control', 'entrypoint']
- symbol_cap_per_file: 20
- module_budget_ratio: 0.35
- module_token_estimates: {'.': 1428, 'algocheck': 8, 'assets': 16, 'benchmarks': 16, 'booster_home': 1420, 'docs': 24, 'skills': 104, 'tests': 764}

## Symbols

.gitignore:
  roles: config

AGENTS.md:

CHANGELOG.md:

CONTRIBUTING.md:

COOKBOOK.md:

MANIFEST.in:

MARKETPLACE.md:

README.md:

README.ru.md:

README.zh-CN.md:

RECOMENDET_PROMPT.md:

chunker.py:
  def semantic_chunks (line 3)

city_server.py:
  def _code_city_path (line 35)
  def set_indexer (line 39)
  def ensure_watch_started (line 47)
  def get_indexer (line 62)
  def CodeCityHandler (line 77)
  def send_json_response (line 80)
  def send_html_response (line 90)
  def do_OPTIONS (line 98)
  def do_GET (line 106)
  def do_POST (line 129)
  def handle_index (line 160)
  def handle_list_repos (line 165)
  def handle_stats (line 176)
  def handle_get_code_city (line 208)
  def handle_serve_code_city (line 236)
  def handle_get_repo_map (line 255)
  def handle_add_repo (line 281)
  def handle_remove_repo (line 345)
  def handle_reindex_repo (line 366)
  def handle_generate_city (line 415)
  +3 symbols omitted by per-file cap

cli.py:
  roles: entrypoint
  def _positive_integer (line 35)
  def _format_bytes (line 45)
  def _context_window (line 55)
  def _worker_count (line 61)
  def _build_parser (line 67)
  def _add_connection_arguments (line 306)
  def _add_repository_binding_arguments (line 320)
  def _resolve_config (line 337)
  def _expand (line 362)
  def _print_json (line 417)
  def _control_status (line 421)
  def _print_control_status (line 432)
  def _print_connection_result (line 463)
  def _print_scan_result (line 477)
  def _print_doctor_result (line 494)
  def _run_control_menu (line 504)
  def _control (line 597)
  def _home_config (line 702)
  def _home_status (line 728)
  def _home_doctor (line 773)
  +4 symbols omitted by per-file cap

code_city.html:

cognitive_runtime.py:
  def _utc_now (line 32)
  def _last_identifier (line 36)
  def _callee_matches (line 41)
  def CognitiveRuntime (line 48)
  def __init__ (line 51)
  def _resolve_repo (line 56)
  def _memory_file (line 69)
  def _load_memory (line 74)
  def _save_memory (line 86)
  def _inside_repo (line 101)
  def _relative (line 108)
  def _resolve_paths (line 114)
  def _run_process (line 136)
  def _symbol_records (line 177)
  def impact_analysis (line 199)
  def _suggest_tests (line 337)
  def _rank_risk (line 370)
  def git_intelligence (line 385)
  def _resolve_git_target (line 437)
  def _parse_git_log (line 455)
  +38 symbols omitted by per-file cap

context7_bridge.py:
  def setup_context7_bridge (line 4)
  def fetch_stack_docs (line 11)

context_provider.py:
  def get_repo_artifacts_status (line 9)
  def get_file_status (line 14)
  def setup_context_provider (line 59)
  def get_repo_map_resource (line 65)
  def get_repo_artifacts_resource (line 85)
  def get_repo_stack_resource (line 97)
  def get_repo_conventions_resource (line 112)
  def get_repo_artifacts (line 146)
  def inject_context (line 162)

control.py:
  def ControlError (line 21)
  def ConnectionTarget (line 26)
  def resolve_project (line 36)
  def runtime_info (line 44)
  def _platform_name (line 65)
  def _user_home (line 69)
  def vscode_user_config_path (line 73)
  def claude_user_config_path (line 90)
  def resolve_connection_target (line 113)
  def _read_json_object (line 162)
  def _atomic_write_json (line 179)
  def _server_store (line 203)
  def build_server_definition (line 212)
  def connect (line 245)
  def disconnect (line 305)
  def connection_status (line 353)
  def scan_settings (line 400)
  def update_scan_settings (line 412)
  def artifact_status (line 439)
  def doctor (line 454)
  +4 symbols omitted by per-file cap

dsa.json:

embedder.py:
  def Embedder (line 6)
  def __init__ (line 7)
  def _ensure_model (line 12)
  def embed (line 19)

file_lock.py:
  def cross_process_file_lock (line 11)

flipchart.py:
  def Flipchart (line 9)
  def __init__ (line 12)
  def generate_call_graph_mermaid (line 16)
  def generate_import_graph_mermaid (line 45)
  def generate_sequence_diagram (line 61)
  def _trace_execution (line 83)
  def _safe_id (line 115)
  def create_session (line 125)
  def add_note (line 145)
  def get_board (line 163)
  def quick_debug (line 178)
  def setup_flipchart_tools (line 211)
  def flipchart_quick_debug (line 216)
  def flipchart_create_session (line 224)
  def flipchart_add_note (line 232)
  def flipchart_get_board (line 241)
  def flipchart_call_graph (line 248)
  def flipchart_sequence_diagram (line 255)

graphs.py:
  def Graphs (line 3)
  def __init__ (line 4)
  def clear_file (line 13)
  def add_call (line 25)
  def add_import (line 30)
  def calls (line 37)
  def imports (line 41)
  def snapshot (line 45)
  def clone (line 54)

indexer.py:
  def IndexCancelled (line 15)
  def IndexGeneration (line 20)
  def RepoIndexer (line 30)
  def __init__ (line 31)
  def _operation_lock (line 50)
  def operation_lock (line 59)
  def extract_data (line 63)
  def index_file (line 125)
  def _index_file_unlocked (line 129)
  def _index_file_in_state (line 132)
  def _staging_state (line 178)
  def build_generation (line 199)
  def scan_progress (line 209)
  def promote_generation (line 252)
  def full_index (line 270)
  def index_repo (line 274)
  def search (line 302)
  def hybrid_search (line 308)
  def _remove_file_unlocked (line 315)
  def remove_file (line 320)
  +6 symbols omitted by per-file cap

indexing_jobs.py:
  def IndexJobManager (line 15)
  def __init__ (line 23)
  def _condition (line 34)
  def _now (line 42)
  def _iso_now (line 46)
  def _notify (line 51)
  def start (line 56)
  def _run (line 119)
  def update (line 137)
  def progress (line 160)
  def _started_at (line 184)
  def mark_running (line 188)
  def finish (line 198)
  def is_cancel_requested (line 208)
  def cancel (line 212)
  def get (line 231)
  def wait (line 242)
  def snapshot (line 266)

install.ps1:

parser_router.py:
  roles: control
  def ParserRouter (line 17)
  def __init__ (line 18)
  def get (line 21)

pyproject.toml:
  roles: config

repomap.py:
  def load_ignore (line 16)
  def load_local_ignore (line 94)
  def RepoMap (line 118)
  def __init__ (line 121)
  def get_repo_map (line 144)
  def get_architecture_map (line 157)
  def get_symbol_map (line 162)
  def coverage_summary (line 167)
  def _collect_all_files (line 171)
  def _records (line 185)
  def _relative_name (line 208)
  def _module_name (line 215)
  def _roles (line 220)
  def _architecture_score (line 241)
  def _select_records (line 256)
  def estimated_tokens (line 274)
  def _render (line 340)
  def _get_tags (line 361)
  def _traverse_tree (line 396)
  def _find_name_node (line 434)
  +1 symbols omitted by per-file cap

repository_lifecycle.py:
  def _utc_now (line 30)
  def _atomic_write_json (line 34)
  def _atomic_copy (line 51)
  def _sha256_file (line 65)
  def RepositoryRegistry (line 73)
  def __init__ (line 76)
  def normalize (line 87)
  def _key (line 91)
  def _record_path (line 94)
  def _read_record (line 97)
  def list_records (line 106)
  def list_repos (line 121)
  def get (line 124)
  def add (line 130)
  def update (line 144)
  def remove (line 159)
  def RepositorySnapshotStore (line 170)
  def __init__ (line 173)
  def _git (line 180)
  def _git_state (line 196)
  +4 symbols omitted by per-file cap

repository_scanner.py:
  def ScanConfig (line 109)
  def __post_init__ (line 120)
  def for_profile (line 132)
  def load (line 142)
  def with_overrides (line 178)
  def to_dict (line 183)
  def save (line 197)
  def IgnoreRules (line 209)
  def from_repository (line 217)
  def ignores_directory (line 258)
  def ignores_file (line 261)
  def _matches_pattern (line 264)
  def ScanResult (line 278)
  def to_dict (line 292)
  def save_report (line 313)
  def RepositoryScanner (line 324)
  def __init__ (line 327)
  def scan (line 332)
  def _result (line 454)
  def _directory_sort_key (line 478)
  +2 symbols omitted by per-file cap

server.py:
  roles: entrypoint
  def _unique_repos (line 39)
  def _startup_repos (line 50)
  def on_index_callback (line 60)
  def _utc_now (line 133)
  def _sync_registered_repos (line 137)
  def _initialize_runtime (line 150)
  def _start_city_web (line 161)
  def _set_index_job (line 175)
  def _index_jobs_snapshot (line 185)
  def _registry_records_for_repos (line 195)
  def _index_state (line 204)
  def _require_search_ready (line 223)
  def _ensure_watch_started (line 237)
  def on_repository_change (line 240)
  def _index_repo_job (line 249)
  def progress (line 256)
  def _start_index_repo_job (line 337)
  def semantic_search (line 353)
  def hybrid_search (line 360)
  def find_symbol (line 367)
  +14 symbols omitted by per-file cap

skill_installer.py:
  def list_bundled_skills (line 10)
  def install_bundled_skills (line 22)
  def auto_install_bundled_skills (line 93)

toolkit.py:
  def CodeToolkit (line 17)
  def __init__ (line 20)
  def _symbols_snapshot (line 24)
  def _get_repo_memory_file (line 30)
  def _load_repo_memory (line 36)
  def _save_repo_memory (line 46)
  def code_grep (line 53)
  def read_with_context (line 96)
  def read_file (line 130)
  def git_diff (line 157)
  def git_log (line 201)
  def run_command (line 238)
  def analyze_error (line 272)
  def list_configs (line 317)
  def project_memory (line 389)
  def compare_symbols (line 434)
  def extract_symbol_content (line 436)
  def find_duplicates (line 482)
  def external_deps (line 535)
  def setup_toolkit_tools (line 631)
  +12 symbols omitted by per-file cap

vector_index.py:
  def VectorIndex (line 13)
  def __init__ (line 16)
  def _tokenize (line 29)
  def _normalize_vector (line 40)
  def _mark_lexical_index_dirty (line 49)
  def _ensure_bm25 (line 52)
  def _dense_candidates (line 65)
  def remove_file (line 78)
  def add (line 89)
  def search (line 105)
  def hybrid_search (line 109)
  def add_rank (line 126)
  def clone (line 179)

visualizer.py:
  def CodeCityVisualizer (line 15)
  def __init__ (line 61)
  def collect_file_metrics (line 68)
  def _parse_metrics (line 137)
  def _calculate_weight (line 176)
  def _get_district (line 186)
  def _get_color (line 206)
  def generate_city_layout (line 233)
  def _layout_buildings (line 297)
  def _generate_connections (line 364)
  def generate_html (line 403)
  def generate_visualization (line 922)

watcher.py:
  def RepoWatcher (line 14)
  def __init__ (line 15)
  def add_repository (line 24)
  def schedule_repository (line 32)
  def _repo_for_path (line 38)
  def _should_index (line 48)
  def on_modified (line 64)
  def on_created (line 76)
  def on_deleted (line 88)
  def on_any_event (line 108)
  def start_watch (line 123)

algocheck/Booster LeetCode check.md:

assets/booster-pipeline.svg:

assets/home-runtime.svg:

benchmarks/home_context_benchmark.py:
  def TargetedFooServiceWorldModel (line 26)
  def enrich (line 29)
  def run (line 47)

booster_home/adapters/booster.py:
  def EnrichmentResult (line 14)
  def BoosterWorldModelAdapter (line 21)
  def __init__ (line 24)
  def enrich (line 37)
  def _enrich_sync (line 49)
  def _infer_target (line 102)

booster_home/adapters/diagnostics.py:
  def DiagnosticCollection (line 13)
  def __iter__ (line 19)
  def __len__ (line 22)
  def DiagnosticSource (line 26)
  def collect (line 27)
  def CognitiveRuntimeDiagnosticSource (line 32)
  def __init__ (line 35)
  def collect (line 39)

booster_home/adapters/lsp.py:
  def LspProtocolError (line 15)
  def encode_lsp_message (line 19)
  def read_lsp_message (line 24)
  def write_lsp_message (line 54)
  def path_to_file_uri (line 64)
  def file_uri_to_path (line 68)
  def LspClient (line 80)
  def __init__ (line 83)
  def start (line 90)
  def _read_until_response (line 122)
  def diagnostics (line 132)
  def close (line 198)
  def _LspSource (line 226)
  def collect (line 230)
  def PyrightDiagnosticSource (line 254)
  def RustAnalyzerDiagnosticSource (line 259)
  def TypeScriptLanguageServerDiagnosticSource (line 264)
  def _language_id (line 269)
  def _source_files (line 280)

booster_home/api/__init__.py:
  roles: contract

booster_home/api/gateway.py:
  roles: contract
  def _error_payload (line 27)
  def _await_if_needed (line 38)
  def _local_bind (line 42)
  def create_gateway_router (line 50)
  def _authorize (line 51)
  def _prepare (line 73)
  def health (line 140)
  def models (line 146)
  def status (line 163)
  def chat_completions (line 167)
  def complete (line 200)
  def responses (line 238)
  def complete (line 316)
  def events (line 371)

booster_home/api/models.py:
  roles: contract
  def _text_content (line 11)
  def responses_input_to_messages (line 24)
  def messages_to_responses_input (line 49)
  def chat_response_to_responses (line 60)

booster_home/api/streaming.py:
  roles: contract
  def forward_stream (line 8)

booster_home/app.py:
  roles: entrypoint
  def create_app (line 13)
  def lifespan (line 21)
  def run_home (line 35)

booster_home/config.py:
  def _ConfigModel (line 17)
  def _local_bind (line 23)
  def HomeSettings (line 31)
  def normalize_auth_token (line 40)
  def validate_network (line 49)
  def UpstreamSettings (line 62)
  def validate_upstream (line 73)
  def ContextSettings (line 85)
  def validate_context (line 99)
  def WorkerSettings (line 120)
  def validate_workers (line 128)
  def MemorySettings (line 140)
  def validate_memory (line 147)
  def RoutingModel (line 157)
  def RoutingSettings (line 163)
  def TelemetrySettings (line 168)
  def ResearchSettings (line 172)
  def validate_research (line 188)
  def HomeConfig (line 210)
  def normalize_flat_values (line 228)
  +13 symbols omitted by per-file cap

booster_home/context/compiler.py:
  def ContextCompiler (line 35)
  def __init__ (line 38)
  def compile (line 67)
  def _classify (line 221)
  def _active_task (line 265)
  def _noise_score (line 272)
  def _apply_worker_results (line 284)
  def _allocate (line 312)

booster_home/context/deterministic.py:
  def strip_ansi (line 15)
  def collapse_duplicate_lines (line 19)
  def collapse_progress (line 36)
  def fold_stack_trace (line 48)
  def compact_success_noise (line 67)
  def normalize_structured_output (line 80)
  def deterministic_normalize (line 92)

booster_home/context/diagnostic.py:
  def Diagnostic (line 12)
  def model_post_init (line 30)
  def _from_item (line 47)
  def normalize_diagnostics (line 64)
  def DiagnosticLifecycle (line 93)
  def update (line 98)

booster_home/context/packer.py:
  def PackingError (line 10)
  def ContextPacker (line 14)
  def __init__ (line 17)
  def _message (line 20)
  def _role_for (line 31)
  def pack (line 48)

booster_home/context/tokenizer.py:
  def TokenCounter (line 11)
  def count_text (line 14)
  def count_messages (line 16)
  def ApproximateTokenCounter (line 19)
  def __init__ (line 22)
  def count_text (line 28)
  def count_messages (line 33)
  def KnownTokenizerCounter (line 37)
  def __init__ (line 40)
  def count_text (line 43)
  def count_messages (line 47)
  def build_token_counter (line 51)

booster_home/mcp.py:
  def setup_home_tools (line 16)
  def unavailable (line 19)
  def ensure_runtime (line 22)
  def home_status (line 29)
  def session_status (line 35)
  def context_stats (line 48)
  def retrieve_session_artifact (line 62)
  def _delegate (line 83)
  def delegate_local (line 94)
  def local_code_review (line 105)
  def local_test_analysis (line 112)
  def local_log_analysis (line 119)
  def local_summarize (line 126)
  def research_service (line 132)
  def research_call (line 138)
  def project_snapshot (line 148)
  def experiment_state (line 160)
  def artifact_lookup (line 172)
  def log_digest (line 184)
  def compare_runs (line 200)
  +6 symbols omitted by per-file cap

booster_home/memory/artifact_store.py:
  def redact_sensitive (line 36)
  def ArtifactMetadata (line 52)
  def ArtifactStore (line 69)
  def __init__ (line 72)
  def _lock (line 77)
  def _safe_session_id (line 81)
  def _session_dir (line 86)
  def _compress (line 92)
  def _decompress (line 99)
  def _atomic_write (line 109)
  def store (line 125)
  def _paths_for_ref (line 181)
  def retrieve (line 191)
  def retrieve_fragment (line 207)
  def list_metadata (line 221)

booster_home/memory/models.py:
  def MemoryModel (line 11)
  def utc_now (line 15)
  def Session (line 19)
  def Episode (line 27)
  def Fact (line 36)
  def Decision (line 49)
  def WorkingSet (line 61)
  def TimelineEvent (line 73)

booster_home/memory/pager.py:
  def ContextIntegrityError (line 8)
  def MemoryPager (line 12)
  def __init__ (line 15)
  def persist_before_evict (line 19)
  def retrieve (line 42)

booster_home/memory/session_store.py:
  def SessionStore (line 20)
  def __init__ (line 23)
  def _lock (line 29)
  def _safe_id (line 37)
  def _path (line 43)
  def _atomic_json (line 51)
  def resolve_id (line 63)
  def resolve_session (line 88)
  def get_or_create (line 99)
  def context (line 119)
  def append_event (line 128)
  def read_events (line 159)
  def update_working_set (line 174)
  def get_working_set (line 183)
  def set_active (line 188)
  def list_sessions (line 200)
  def delete (line 210)
  def cleanup (line 223)

booster_home/models.py:
  def HomeModel (line 17)
  def ContextPolicy (line 23)
  def ContextCategory (line 32)
  def Priority (line 53)
  def Message (line 63)
  def text (line 73)
  def ChatCompletionRequest (line 88)
  def validate_max_tokens (line 98)
  def upstream_payload (line 103)
  def ResponsesRequest (line 111)
  def validate_max_output_tokens (line 121)
  def upstream_payload (line 126)
  def ModelProfile (line 134)
  def validate_context_window (line 150)
  def ContextBlock (line 156)
  def ContextOperation (line 174)
  def CompiledContext (line 185)
  def SessionContext (line 202)
  def RequestContext (line 211)
  def WorkerJob (line 219)
  +1 symbols omitted by per-file cap

booster_home/research/analysis.py:
  def _canonical (line 54)
  def _numeric (line 58)
  def _flatten (line 73)
  def read_rows (line 82)
  def metric_series (line 123)
  def _field_for_extract (line 133)
  def _trend (line 144)
  def regime_signature (line 168)
  def scientific_digest (line 177)
  def compare_run_records (line 274)

booster_home/research/models.py:
  def ResearchModel (line 11)
  def ResearchMode (line 17)
  def HypothesisStatus (line 27)
  def WorkerRole (line 38)
  def CheckpointRecord (line 50)
  def HypothesisRecord (line 69)
  def validate_confidence (line 90)
  def ResearchBlock (line 96)

booster_home/research/service.py:
  def _words (line 57)
  def _json_text (line 61)
  def _redact (line 71)
  def _redact_value (line 75)
  def _relative (line 88)
  def _record_tokens (line 92)
  def ResearchService (line 96)
  def __init__ (line 99)
  def _store (line 115)
  def _priority (line 125)
  def project_snapshot (line 139)
  def _memory_context (line 252)
  def _metric_run_summaries (line 269)
  def experiment_state (line 292)
  def _resolve_reference (line 365)
  def artifact_lookup (line 380)
  def log_digest (line 470)
  def compare_runs (line 502)
  def _hypotheses (line 535)
  def hypothesis_register (line 549)
  +7 symbols omitted by per-file cap

booster_home/research/store.py:
  def ResearchInputError (line 52)
  def _utc_now (line 56)
  def _token_count (line 62)
  def _normalise_key (line 66)
  def _walk_values (line 70)
  def _find_value (line 80)
  def ResearchStateStore (line 87)
  def __init__ (line 90)
  def resolve_path (line 97)
  def is_checkpoint (line 111)
  def _ignored (line 114)
  def iter_files (line 127)
  def read_text (line 159)
  def _sidecar_candidates (line 174)
  def checkpoint_metadata (line 182)
  def state_path (line 235)
  def load_state (line 238)
  def _atomic_json (line 255)
  def save_state (line 268)
  def update_state (line 275)
  +3 symbols omitted by per-file cap

booster_home/runtime.py:
  def HomeDependencies (line 35)
  def HomeRuntime (line 49)
  def __init__ (line 52)
  def start (line 84)
  def _ensure_legacy_bridge (line 151)
  def _maintenance_loop (line 176)
  def resolve_session (line 184)
  def event (line 204)
  def status (line 210)
  def health (line 251)
  def close (line 258)
  def build_runtime (line 278)

booster_home/telemetry/logging.py:
  def redact_endpoint (line 12)
  def redact_mapping (line 26)
  def RedactedLogger (line 40)
  def __init__ (line 43)
  def log (line 53)
  def info (line 64)
  def warning (line 67)
  def error (line 70)

booster_home/telemetry/metrics.py:
  def MetricsRegistry (line 12)
  def __init__ (line 15)
  def increment (line 21)
  def observe (line 25)
  def timer (line 32)
  def snapshot (line 39)

booster_home/upstream/discovery.py:
  def ModelDiscovery (line 14)
  def __init__ (line 17)
  def refresh (line 32)
  def list_models (line 39)
  def profile (line 48)
  def discover (line 82)
  def _registry_profile (line 87)

booster_home/upstream/provider.py:
  def UpstreamProvider (line 16)
  def models (line 19)
  def chat_completions (line 21)
  def chat_completions_stream (line 23)
  def responses (line 25)
  def responses_stream (line 27)
  def close (line 29)
  def _safe_error_text (line 32)
  def OpenAICompatibleProvider (line 41)
  def __init__ (line 44)
  def _url (line 53)
  def _headers (line 56)
  def _request_json (line 60)
  def models (line 116)
  def chat_completions (line 122)
  def responses (line 125)
  def _stream (line 128)
  def chat_completions_stream (line 166)
  def responses_stream (line 169)
  def close (line 172)

booster_home/workers/client.py:
  def ContextWorkerBackend (line 15)
  def execute (line 18)
  def OpenAICompatibleWorkerBackend (line 21)
  def __init__ (line 24)
  def _model (line 39)
  def _cache_key (line 50)
  def _extract_content (line 59)
  def _request (line 75)
  def execute (line 101)

booster_home/workers/schemas.py:
  roles: contract
  def WorkerPayload (line 11)
  def _extract_json (line 28)
  def parse_worker_payload (line 43)

docs/API.md:

docs/ARCHITECTURE.md:

docs/RELEASE.md:

skills/__init__.py:

skills/booster-architecture-map/SKILL.md:

skills/booster-bug-hunt/SKILL.md:

skills/booster-cognitive-runtime/SKILL.md:

skills/booster-context-inject/SKILL.md:

skills/booster-deep-dive/SKILL.md:

skills/booster-feature-add/SKILL.md:

skills/booster-flipchart/SKILL.md:

skills/booster-mcp-workflow/SKILL.md:

skills/booster-onboard/SKILL.md:

skills/booster-project-memory/SKILL.md:

skills/booster-refactor/SKILL.md:

skills/booster-review/SKILL.md:

tests/home/__init__.py:

tests/home/conftest.py:
  def FakeProvider (line 13)
  def __init__ (line 14)
  def models (line 18)
  def chat_completions (line 23)
  def chat_completions_stream (line 44)
  def stream (line 47)
  def responses (line 57)
  def responses_stream (line 66)
  def close (line 69)
  def fake_provider (line 74)

tests/home/test_artifact_store.py:
  def test_artifact_exact_retrieval_and_secret_redaction (line 8)
  def test_artifacts_are_session_isolated (line 25)
  def test_utf8_bytes_are_redacted_before_persistence (line 33)

tests/home/test_budget.py:
  def test_budget_uses_minimum_physical_and_configured_window (line 5)
  def test_unknown_window_has_no_hard_limit (line 18)
  def test_invalid_output_reserve_fails_closed (line 24)

tests/home/test_compiler.py:
  def test_compiler_persists_evicted_raw_block (line 12)
  def test_compiler_fails_closed_when_persistence_is_disabled (line 41)

tests/home/test_config.py:
  def test_config_precedence_and_redaction (line 9)
  def test_invalid_context_budget_is_rejected (line 33)
  def test_redacted_config_removes_endpoint_query_secret (line 38)
  def test_non_loopback_home_requires_auth_token (line 46)

tests/home/test_delegation.py:
  def Backend (line 9)
  def execute (line 10)
  def test_delegation_uses_shared_pool (line 17)

tests/home/test_deterministic.py:
  def test_ansi_duplicates_and_progress_are_compacted (line 9)
  def test_structured_json_remains_json_and_unicode_survives (line 15)

tests/home/test_diagnostic_lifecycle.py:
  def test_diagnostic_change_and_reappearance_are_distinguished (line 3)

tests/home/test_gateway.py:
  def _config (line 19)
  def test_gateway_preserves_unknown_chat_fields_and_redacts_status (line 32)
  def test_gateway_requires_auth_for_non_loopback_bind (line 54)
  def test_gateway_stream_and_responses (line 71)
  def test_responses_chat_fallback_uses_compiled_messages (line 93)
  def missing_responses (line 101)
  def test_models_endpoint_has_bounded_discovery_fallback (line 119)
  def slow_models (line 123)
  def test_chat_profile_discovery_has_bounded_fallback (line 135)
  def slow_models (line 139)

tests/home/test_lsp.py:
  def test_lsp_content_length_framing (line 10)

tests/home/test_models.py:
  def test_provider_reasoning_content_survives_compilation (line 7)

tests/home/test_packer.py:
  def test_packer_keeps_protected_blocks_and_order (line 4)

tests/home/test_project_memory.py:
  def Runtime (line 6)
  def remember_project_fact (line 7)
  def test_only_validated_decisions_are_promoted (line 12)

tests/home/test_research.py:
  def _write_jsonl (line 21)
  def test_project_snapshot_keeps_checkpoint_metadata_only (line 25)
  def test_experiment_state_and_next_experiment_use_local_state (line 55)
  def test_log_digest_and_compare_runs_reject_regime_mismatch (line 95)
  def test_artifact_lookup_checkpoint_registry_and_lightning_trace (line 129)
  def test_context_pack_has_layers_budget_and_no_binary_content (line 195)
  def test_research_mcp_tool_names_are_explicit (line 217)
  def _WorkerProvider (line 237)
  def __init__ (line 238)
  def models (line 241)
  def chat_completions (line 244)
  def chat_completions_stream (line 248)
  def responses (line 251)
  def responses_stream (line 254)
  def close (line 257)
  def test_worker_output_budget_is_forwarded (line 261)
  def test_policy_off_still_fails_on_known_hard_budget (line 278)

tests/home/test_responses.py:
  def test_responses_rejects_unsupported_input (line 15)
  def test_responses_rejects_unsupported_content_part (line 30)

tests/home/test_session_store.py:
  def test_session_resolution_and_timeline_are_isolated (line 13)
  def test_session_store_serializes_writes_across_processes (line 26)

tests/home/test_telemetry.py:
  def test_telemetry_redacts_secret_and_validates_envelope (line 3)
  def test_telemetry_redacts_nested_secret_values (line 16)

tests/home/test_upstream.py:
  def test_provider_preserves_path_unknown_fields_and_auth (line 12)
  def handler (line 15)
  def test_provider_does_not_retry_client_errors (line 39)
  def handler (line 42)

tests/home/test_workers.py:
  roles: control
  def SlowBackend (line 10)
  def __init__ (line 11)
  def execute (line 15)
  def test_worker_pool_is_bounded (line 24)

tests/test_city_server.py:
  def test_code_city_uses_canonical_booster_artifact_directory (line 13)
  def test_code_city_api_serves_registered_artifact (line 19)

tests/test_cognitive_runtime.py:
  def make_runtime (line 13)
  def test_impact_analysis_traces_callers_and_callees (line 47)
  def test_project_memory_recall_filters_structured_facts (line 61)
  def test_project_memory_rejects_corrupt_json_and_writes_valid_json (line 77)
  def test_collect_diagnostics_reports_python_syntax_error (line 91)
  def test_collect_diagnostics_fails_closed_on_external_tool_timeout (line 109)
  def fake_which (line 115)
  def fake_run_process (line 120)
  def test_security_audit_reports_missing_scanners_as_incomplete (line 148)
  def test_security_audit_keeps_high_findings_failed_when_other_scanner_missing (line 161)
  def fake_which (line 167)
  def fake_run_process (line 170)
  def test_collect_diagnostics_parses_ruff_findings (line 206)
  def fake_which (line 212)
  def fake_run_process (line 217)
  def test_git_intelligence_reads_file_history (line 255)

tests/test_context_provider.py:
  def FakeMCP (line 6)
  def __init__ (line 7)
  def resource (line 11)
  def register (line 12)
  def tool (line 18)
  def register (line 19)
  def test_repo_map_resource_creates_missing_cache_entry (line 26)
  def test_artifact_status_reports_canonical_paths (line 44)
  def test_artifact_resource_and_tool_return_matching_status (line 61)

tests/test_control.py:
  def write_json (line 18)
  def test_connect_workspace_preserves_other_servers_and_creates_backup (line 23)
  def test_user_connection_is_portable_unless_repository_is_explicit (line 44)
  def test_connect_and_disconnect_claude_user_config_on_macos_path (line 77)
  def test_control_scan_settings_and_cli_connect_are_scoped_to_project (line 106)
  def test_cli_user_connection_does_not_bind_repository (line 133)
  def test_launcher_is_generated_for_windows_and_unix_without_touching_path (line 157)
  def test_runtime_info_prefers_project_virtualenv_over_system_python (line 172)

tests/test_hybrid_search.py:
  def build_index (line 3)
  def test_hybrid_search_matches_camel_case_identifier_from_snake_case_query (line 36)
  def test_hybrid_search_removes_deleted_file_from_dense_and_lexical_indexes (line 46)
  def test_dense_search_keeps_its_existing_result_shape (line 56)

tests/test_index_jobs.py:
  def test_index_job_manager_returns_before_slow_worker_and_supports_cancel (line 8)
  def worker (line 13)
  def test_index_job_manager_coalesces_duplicate_requests (line 43)
  def worker (line 48)

tests/test_indexer.py:
  def test_index_repo_removes_files_deleted_since_previous_scan (line 7)
  def fake_index_file (line 17)

tests/test_repomap.py:
  def _write (line 8)
  def test_architecture_map_keeps_modules_and_caps_giant_file (line 13)

tests/test_repository_lifecycle.py:
  def git (line 8)
  def test_repository_registry_survives_a_new_process_view (line 19)
  def test_repository_registry_serializes_cross_process_updates (line 54)
  def test_snapshot_history_is_immutable_and_commit_bound (line 92)

tests/test_repository_scanner.py:
  def write_source (line 9)
  def test_scanner_respects_ignore_rules_depth_and_size_budgets (line 16)
  def test_cli_expand_writes_map_report_and_persistent_scan_config (line 40)
  def test_repo_map_and_indexer_reuse_the_saved_scan_budget (line 58)

tests/test_runtime_hardening.py:
  def test_full_index_delegates_to_single_repo_indexing (line 7)
  def fake_index_repo (line 12)
  def test_code_city_port_zero_logs_actual_bound_port (line 23)
  def FakeHTTPServer (line 29)
  def __init__ (line 30)
  def serve_forever (line 35)
  def shutdown (line 38)

tests/test_server_index_jobs.py:
  def test_server_index_job_is_background_and_waitable (line 10)
  def fake_build_generation (line 23)

tests/test_server_scope.py:
  def test_workspace_bound_server_does_not_import_unrelated_registry_repositories (line 10)
  def test_search_does_not_return_silent_empty_results_while_indexing (line 23)
  def EmptyIndexer (line 24)
  def stats (line 27)

tests/test_skill_installer.py:
  def test_bundled_skills_are_discoverable (line 3)

tests/test_visualizer.py:
  def test_code_city_layout_is_compact_and_html_autoframes (line 5)

tests/test_watcher.py:
  def FakeIndexer (line 6)
  def __init__ (line 7)
  def index_file (line 10)
  def FakeObserver (line 14)
  def __init__ (line 15)
  def schedule (line 18)
  def file_event (line 22)
  def test_watcher_respects_repository_scanner_ignore_rules (line 26)
  def test_watcher_schedules_a_repository_only_once (line 44)
