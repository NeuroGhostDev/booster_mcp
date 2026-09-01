"""Thin application facade over the existing Booster runtime."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from repomap import RepoMap
from repository_lifecycle import RepositorySnapshotStore
from visualizer import CodeCityVisualizer

from .cache import ReadOnlyCache
from .models import (
    ArchitecturePayload,
    ArchitectureRequest,
    ArchitectureResult,
    DiagnosticFinding,
    DiagnosticsPayload,
    DiagnosticsRequest,
    DiagnosticsResult,
    DiagnosticsSummary,
    FocusSymbolPayload,
    FocusSymbolResult,
    HistoryBlame,
    HistoryCommit,
    HistoryPayload,
    HistoryRequest,
    HistoryResult,
    ImpactConnection,
    ImpactPayload,
    ImpactRequest,
    ImpactResult,
    ImpactRisk,
    RelatedTest,
    RelatedTestsPayload,
    RelatedTestsRequest,
    RelatedTestsResult,
    RepositoryMetadata,
    SearchMatch,
    SearchPayload,
    SearchRequest,
    SearchResult,
    SnapshotComparePayload,
    SnapshotCompareRequest,
    SnapshotCompareResult,
    SnapshotConnectionDiff,
    SnapshotListPayload,
    SnapshotListResult,
    SnapshotReference,
    StatusPayload,
    SymbolFocusRequest,
    SymbolLocation,
    UIFocus,
    UIState,
)
from .security import RepositoryAllowlist

SymbolLookup = Callable[[str], Any]
SearchLookup = Callable[[str, int], Any]
ImpactLookup = Callable[[str, str, int], Any]
HistoryLookup = Callable[[str | None, str | None, str, int], Any]
DiagnosticsLookup = Callable[[list[str], str, bool, bool, int], Any]
StatusProvider = Callable[[], Mapping[str, Any]]
SnapshotFactory = Callable[[Path], RepositorySnapshotStore]


class FacadeError(RuntimeError):
    """An expected, browser-safe application error."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class BoosterFacade:
    """Expose read-only Observatory operations without owning repository logic."""

    def __init__(
        self,
        indexer: Any,
        repositories: RepositoryAllowlist | Mapping[str, str | Path] | None = None,
        *,
        repository_registry: Any | None = None,
        symbol_lookup: SymbolLookup | None = None,
        search_lookup: SearchLookup | None = None,
        impact_lookup: ImpactLookup | None = None,
        history_lookup: HistoryLookup | None = None,
        diagnostics_lookup: DiagnosticsLookup | None = None,
        status_provider: StatusProvider | None = None,
        snapshot_factory: SnapshotFactory = RepositorySnapshotStore,
        mode: str | None = None,
        webmcp: bool = True,
        city_artifact_dir: str | Path | None = None,
        cache: ReadOnlyCache | None = None,
        snapshot_artifacts_dir: str | Path | None = None,
        precomputed_history: Mapping[str, Any] | None = None,
        precomputed_diagnostics: Mapping[str, Any] | None = None,
    ) -> None:
        self.indexer = indexer
        self.repositories = (
            repositories
            if isinstance(repositories, RepositoryAllowlist)
            else RepositoryAllowlist(repositories, registry=repository_registry)
        )
        self.repository_registry = repository_registry
        self.symbol_lookup = symbol_lookup or self._indexer_symbol_lookup
        self.search_lookup = search_lookup or self._indexer_search_lookup
        self.impact_lookup = impact_lookup or self._indexer_impact_lookup
        self.history_lookup = history_lookup or self._indexer_history_lookup
        self.diagnostics_lookup = diagnostics_lookup or self._indexer_diagnostics_lookup
        self.status_provider = status_provider
        self.snapshot_factory = snapshot_factory
        self.mode = mode or os.getenv("BOOSTER_WEB_MODE", "local")
        self.webmcp = webmcp
        self.city_artifact_dir = (
            Path(city_artifact_dir).expanduser().resolve()
            if city_artifact_dir is not None
            else None
        )
        self.cache = cache or ReadOnlyCache()
        self._known_generations: dict[str, str] = {}
        self.snapshot_artifacts_dir = (
            Path(snapshot_artifacts_dir).expanduser().resolve()
            if snapshot_artifacts_dir is not None
            else None
        )
        self.precomputed_history = precomputed_history
        self.precomputed_diagnostics = precomputed_diagnostics

    def _indexer_symbol_lookup(self, query: str) -> Any:
        find_symbols = getattr(self.indexer, "find_symbols", None)
        if not callable(find_symbols):
            raise FacadeError("INTERNAL_ERROR", "Symbol lookup is unavailable")
        return find_symbols(query)

    def _indexer_search_lookup(self, query: str, limit: int) -> Any:
        hybrid_search = getattr(self.indexer, "hybrid_search", None)
        if not callable(hybrid_search):
            raise FacadeError("INTERNAL_ERROR", "Code search is unavailable")
        return hybrid_search(query, k=limit)

    def _indexer_impact_lookup(self, target: str, repo: str, max_depth: int) -> Any:
        impact_analysis = getattr(self.indexer, "impact_analysis", None)
        if not callable(impact_analysis):
            raise FacadeError("INTERNAL_ERROR", "Impact analysis is unavailable")
        return impact_analysis(target, repo, max_depth)

    def _indexer_history_lookup(
        self, path: str | None, symbol: str | None, repo: str, limit: int
    ) -> Any:
        git_intelligence = getattr(self.indexer, "git_intelligence", None)
        if not callable(git_intelligence):
            raise FacadeError("INTERNAL_ERROR", "Git history is unavailable")
        return git_intelligence(path, symbol, repo, limit)

    def _indexer_diagnostics_lookup(
        self, paths: list[str], repo: str, include_security: bool, run_external: bool, timeout: int
    ) -> Any:
        collect_diagnostics = getattr(self.indexer, "collect_diagnostics", None)
        if not callable(collect_diagnostics):
            raise FacadeError("INTERNAL_ERROR", "Diagnostics are unavailable")
        return collect_diagnostics(paths, repo, include_security, run_external, timeout)

    def _resolve_repo(self, repo_id: str) -> Path:
        try:
            return self.repositories.resolve_repo(repo_id)
        except ValueError:
            raise FacadeError("INVALID_ARGUMENT", "Invalid repository ID") from None
        except KeyError:
            raise FacadeError("REPO_NOT_FOUND", "Repository is not available") from None

    def _health(self) -> dict[str, Any]:
        method = getattr(self.indexer, "index_health", None)
        if not callable(method):
            return {}
        value = method()
        return dict(value) if isinstance(value, Mapping) else {}

    def _stats(self) -> dict[str, Any]:
        method = getattr(self.indexer, "stats", None)
        if not callable(method):
            return {}
        value = method()
        return dict(value) if isinstance(value, Mapping) else {}

    def _state(self) -> Mapping[str, Any]:
        if self.status_provider is None:
            return {}
        value = self.status_provider()
        return value if isinstance(value, Mapping) else {}

    def _cache_key(
        self, repo_id: str, root: Path, operation: str, arguments: Any
    ) -> tuple[str, str, str, str] | None:
        health = self._health()
        if health.get("repository") not in {None, str(root)}:
            return None
        generation_id = health.get("generation_id")
        if not isinstance(generation_id, str) or not generation_id:
            return None
        previous = self._known_generations.get(repo_id)
        if previous is not None and previous != generation_id:
            self.cache.invalidate_repo(repo_id, generation_id)
        self._known_generations[repo_id] = generation_id
        return self.cache.key(repo_id, generation_id, operation, arguments)

    def inspect_architecture(self, request: ArchitectureRequest) -> ArchitecturePayload:
        root = self._resolve_repo(request.repo_id)
        try:
            architecture_map = RepoMap(root=str(root), indexer=self.indexer).get_architecture_map()
        except Exception as exc:
            raise FacadeError("INTERNAL_ERROR", "Architecture overview failed") from exc
        return ArchitecturePayload(
            repo=self._repository_metadata(request.repo_id, root),
            result=ArchitectureResult(
                focus=request.focus,
                map=architecture_map[:12000],
                stats=self._stats(),
            ),
            ui=UIState(mode="architecture"),
        )

    @staticmethod
    def _commit_from_record(record: Mapping[str, Any] | None) -> str | None:
        if not record:
            return None
        snapshot = record.get("last_snapshot")
        if not isinstance(snapshot, Mapping):
            snapshot = record
        commit = snapshot.get("commit")
        if not isinstance(commit, str) or not commit or commit == "NO_COMMIT":
            return None
        return commit

    def _repository_metadata(self, repo_id: str, root: Path) -> RepositoryMetadata:
        health = self._health()
        record: Mapping[str, Any] | None = None
        if self.repository_registry is not None:
            getter = getattr(self.repository_registry, "get", None)
            if callable(getter):
                candidate = getter(root)
                if isinstance(candidate, Mapping):
                    record = candidate

        generation_id: str | None = None
        if health.get("repository") in {None, str(root)}:
            value = health.get("generation_id")
            if isinstance(value, str) and value:
                generation_id = value
        if generation_id is None and record is not None:
            value = record.get("generation_id")
            if isinstance(value, str) and value:
                generation_id = value

        commit = self._commit_from_record(record)
        if commit is None:
            try:
                latest = self.snapshot_factory(root).latest()
            except (OSError, TypeError, ValueError):
                latest = None
            if isinstance(latest, Mapping):
                commit = self._commit_from_record(latest)

        return RepositoryMetadata(id=repo_id, generation_id=generation_id, commit=commit)

    @staticmethod
    def _normalize_city_value(value: Any, root: Path, key: str | None = None) -> Any:
        if isinstance(value, Mapping):
            return {
                str(item_key): BoosterFacade._normalize_city_value(item_value, root, str(item_key))
                for item_key, item_value in value.items()
            }
        if isinstance(value, list):
            return [BoosterFacade._normalize_city_value(item, root, key) for item in value]
        if key == "file" and isinstance(value, str):
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = root / candidate
            try:
                return candidate.resolve().relative_to(root).as_posix()
            except ValueError:
                return None
        return value

    def city_data(self, repo_id: str) -> dict[str, Any]:
        """Return normalized Code City data from the prepared or existing artifact."""
        root = self._resolve_repo(repo_id)
        artifact_dir = self.city_artifact_dir or (root / ".agents" / "booster")
        artifact_dir = artifact_dir.resolve()
        if not artifact_dir.is_relative_to(root):
            raise FacadeError("FILE_NOT_FOUND", "Code City artifact is unavailable")
        city_file = (artifact_dir / "city.json").resolve()
        if not city_file.is_relative_to(root):
            raise FacadeError("FILE_NOT_FOUND", "Code City artifact is unavailable")

        if city_file.is_file():
            try:
                raw_city = json.loads(city_file.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise FacadeError("INTERNAL_ERROR", "Code City data is invalid") from exc
        elif self.mode == "demo":
            raise FacadeError("FILE_NOT_FOUND", "Prepared Code City data is unavailable")
        else:
            try:
                raw_city = CodeCityVisualizer(self.indexer).generate_city_layout(str(root))
            except Exception as exc:
                raise FacadeError("INTERNAL_ERROR", "Code City generation failed") from exc

        if not isinstance(raw_city, Mapping) or "error" in raw_city:
            raise FacadeError("FILE_NOT_FOUND", "Code City data is unavailable")
        normalized = self._normalize_city_value(raw_city, root)
        if not isinstance(normalized, dict):
            raise FacadeError("INTERNAL_ERROR", "Code City data is invalid")
        normalized["repo"] = ""
        return normalized

    def _demo_history(
        self, path: str | None, symbol: str | None, root: Path, limit: int
    ) -> Mapping[str, Any]:
        if not isinstance(self.precomputed_history, Mapping):
            raise FacadeError("INTERNAL_ERROR", "Prepared history is unavailable")
        records = self.precomputed_history.get("paths")
        if not isinstance(records, Mapping):
            raise FacadeError("INTERNAL_ERROR", "Prepared history is invalid")

        relative_path = path
        if relative_path is None and symbol:
            symbol_files = self._symbol_files(root)
            candidates = sorted(symbol_files.get(symbol, set()))
            if not candidates:
                candidates = sorted(
                    {
                        file_path
                        for name, paths in symbol_files.items()
                        if symbol.lower() in name.lower()
                        for file_path in paths
                    }
                )
            relative_path = candidates[0] if candidates else None
        value = records.get(relative_path) if relative_path is not None else None
        if not isinstance(value, Mapping):
            return {
                "path": relative_path,
                "symbol": symbol,
                "commits": [],
                "blame": [],
                "history_hint": "Precomputed history is unavailable for this target.",
            }

        result = dict(value)
        result["path"] = relative_path or result.get("path")
        result["symbol"] = symbol or result.get("symbol")
        result["commits"] = (
            value.get("commits", [])[:limit] if isinstance(value.get("commits"), list) else []
        )
        result["blame"] = (
            value.get("blame", [])[:limit] if isinstance(value.get("blame"), list) else []
        )
        result.pop("repo", None)
        result.pop("errors", None)
        return result

    def _demo_diagnostics(self, requested_paths: list[str], root: Path) -> Mapping[str, Any]:
        if not isinstance(self.precomputed_diagnostics, Mapping):
            raise FacadeError("INTERNAL_ERROR", "Prepared diagnostics are unavailable")
        raw_checked = self.precomputed_diagnostics.get("paths_checked")
        checked_paths = raw_checked if isinstance(raw_checked, list) else []
        prepared_paths = {
            path
            for raw_path in checked_paths
            if (path := self._normalize_repo_path(raw_path, root)) is not None
        }
        missing = [path for path in requested_paths if path not in prepared_paths]
        if missing:
            raise FacadeError(
                "FILE_NOT_FOUND", "Precomputed diagnostics are unavailable for requested path"
            )

        findings: list[Mapping[str, Any]] = []
        raw_findings = self.precomputed_diagnostics.get("findings")
        if isinstance(raw_findings, list):
            requested = set(requested_paths)
            for item in raw_findings:
                if not isinstance(item, Mapping):
                    continue
                path = self._normalize_repo_path(item.get("file"), root)
                if path in requested:
                    findings.append(item)
        by_severity: dict[str, int] = {}
        for finding in findings:
            severity = finding.get("severity")
            if isinstance(severity, str):
                by_severity[severity] = by_severity.get(severity, 0) + 1
        return {
            "paths_checked": requested_paths,
            "summary": {
                "status": "failed" if findings else "passed",
                "total": len(findings),
                "by_severity": by_severity,
            },
            "findings": [dict(finding) for finding in findings],
        }

    @staticmethod
    def _job_is_active(state: Mapping[str, Any], repo: Path | None) -> bool:
        active = state.get("active")
        if isinstance(active, Mapping):
            if repo is None:
                return bool(active)
            return str(repo) in active
        if state.get("status") in {"queued", "running", "cancelling", "indexing"}:
            return True
        jobs = state.get("jobs")
        if isinstance(jobs, Mapping):
            return any(
                isinstance(job, Mapping)
                and job.get("status") in {"queued", "running", "cancelling"}
                and (repo is None or key == str(repo))
                for key, job in jobs.items()
            )
        return False

    def status(self, repo_id: str | None = None) -> StatusPayload:
        if repo_id is None:
            repo_id = self.repositories.default_repo_id
        if repo_id is None:
            return StatusPayload(
                status="empty",
                mode=self.mode,
                webmcp=self.webmcp,
                capabilities=[
                    "focus",
                    "search",
                    "impact",
                    "history",
                    "diagnostics",
                    "related_tests",
                    "snapshots",
                    "architecture",
                ],
            )

        root = self._resolve_repo(repo_id)
        metadata = self._repository_metadata(repo_id, root)
        health = self._health()
        state = self._state()
        health_matches = health.get("repository") in {None, str(root)}
        ready = bool(health.get("ready")) and health_matches
        if not ready and health_matches:
            stats = self._stats()
            ready = (
                bool(stats.get("generation_id")) and int(stats.get("vectors_in_faiss", 0) or 0) > 0
            )
        if ready:
            status = "ready"
        elif self._job_is_active(state, root):
            status = "indexing"
        else:
            status = "not_ready"

        return StatusPayload(
            status=status,
            mode=self.mode,
            webmcp=self.webmcp,
            repo_id=repo_id,
            generation_id=metadata.generation_id,
            commit=metadata.commit,
            capabilities=[
                "focus",
                "search",
                "impact",
                "history",
                "diagnostics",
                "related_tests",
                "snapshots",
                "architecture",
            ],
            repo=metadata,
        )

    @staticmethod
    def _matches(value: Any) -> tuple[list[Mapping[str, Any]], str | None]:
        if isinstance(value, Mapping):
            raw_matches = value.get("symbols", [])
            error = value.get("error")
        else:
            raw_matches = value
            error = None
        if not isinstance(raw_matches, list):
            raw_matches = []
        matches = [item for item in raw_matches if isinstance(item, Mapping)]
        return matches, error if isinstance(error, str) else None

    def _lookup(self, query: str) -> tuple[list[Mapping[str, Any]], str | None]:
        candidates = [query]
        leaf = query.rsplit(".", 1)[-1]
        if leaf != query:
            candidates.append(leaf)
        last_error: str | None = None
        for candidate in candidates:
            try:
                matches, error = self._matches(self.symbol_lookup(candidate))
            except FacadeError:
                raise
            except Exception as exc:
                raise FacadeError("INTERNAL_ERROR", "Symbol lookup failed") from exc
            if matches:
                return matches, error
            last_error = error or last_error
        return [], last_error

    @staticmethod
    def _normalize_repo_path(raw_path: Any, root: Path) -> str | None:
        if not isinstance(raw_path, (str, Path)) or not str(raw_path):
            return None
        file_path = Path(raw_path)
        if not file_path.is_absolute():
            file_path = root / file_path
        file_path = file_path.expanduser().resolve()
        if not file_path.is_relative_to(root):
            return None
        return file_path.relative_to(root).as_posix()

    @staticmethod
    def _lookup_items(value: Any) -> tuple[list[Mapping[str, Any]], str | None]:
        if isinstance(value, Mapping):
            raw_items = value.get("results", value.get("matches", []))
            error = value.get("error")
        else:
            raw_items = value
            error = None
        if not isinstance(raw_items, list):
            raw_items = []
        return (
            [item for item in raw_items if isinstance(item, Mapping)],
            error if isinstance(error, str) else None,
        )

    def search(self, request: SearchRequest) -> SearchPayload:
        root = self._resolve_repo(request.repo_id)
        cache_key = self._cache_key(request.repo_id, root, "search", request.model_dump())
        if cache_key is not None:
            cached = self.cache.get(cache_key)
            if isinstance(cached, SearchPayload):
                return cached
        try:
            raw_value = self.search_lookup(request.query, request.limit)
        except FacadeError:
            raise
        except Exception as exc:
            if self._lookup_signals_index_error(str(exc)):
                raise FacadeError(
                    "INDEX_NOT_READY", "Repository index is not ready", retryable=True
                ) from exc
            raise FacadeError("INTERNAL_ERROR", "Code search failed") from exc

        raw_matches, lookup_error = self._lookup_items(raw_value)
        if self._lookup_signals_index_error(lookup_error):
            raise FacadeError("INDEX_NOT_READY", "Repository index is not ready", retryable=True)

        by_path: dict[str, SearchMatch] = {}
        for match in raw_matches:
            path = self._normalize_repo_path(match.get("file") or match.get("path"), root)
            if path is None:
                continue
            retrieval = match.get("retrieval")
            raw_score = (
                retrieval.get("score") if isinstance(retrieval, Mapping) else match.get("score")
            )
            try:
                score = float(raw_score) if raw_score is not None else None
            except (TypeError, ValueError):
                score = None
            symbol = match.get("symbol") or match.get("name")
            kind = match.get("kind")
            normalized = SearchMatch(
                path=path,
                symbol=str(symbol) if symbol is not None else None,
                score=score,
                kind=str(kind) if kind is not None else None,
            )
            current = by_path.get(path)
            if current is None or (
                normalized.score is not None
                and (current.score is None or normalized.score > current.score)
            ):
                by_path[path] = normalized

        matches = list(by_path.values())[: request.limit]
        payload = SearchPayload(
            repo=self._repository_metadata(request.repo_id, root),
            result=SearchResult(matches=matches),
            ui=UIState(
                highlights=[match.path for match in matches],
                mode="search",
            ),
        )
        if cache_key is not None:
            self.cache.set(cache_key, payload)
        return payload

    def search_code(self, request: SearchRequest) -> SearchPayload:
        """Named application action for the browser search tool."""
        return self.search(request)

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str)]

    def _symbol_files(self, root: Path) -> dict[str, set[str]]:
        snapshot = getattr(self.indexer, "symbols_snapshot", None)
        raw_symbols = snapshot() if callable(snapshot) else getattr(self.indexer, "symbols", {})
        if not isinstance(raw_symbols, Mapping):
            return {}
        symbol_files: dict[str, set[str]] = {}
        for raw_file, symbols in raw_symbols.items():
            path = self._normalize_repo_path(raw_file, root)
            if path is None or not isinstance(symbols, list):
                continue
            for symbol in symbols:
                if not isinstance(symbol, Mapping) or not isinstance(symbol.get("name"), str):
                    continue
                symbol_files.setdefault(symbol["name"], set()).add(path)
        return symbol_files

    def _normalize_connections(
        self, raw_value: Mapping[str, Any], root: Path
    ) -> list[ImpactConnection]:
        graph = raw_value.get("knowledge_graph")
        edges = graph.get("edges") if isinstance(graph, Mapping) else []
        if not isinstance(edges, list):
            return []
        symbol_files = self._symbol_files(root)
        connections: list[ImpactConnection] = []
        seen: set[tuple[str, str, str]] = set()
        for edge in edges[:200]:
            if not isinstance(edge, Mapping):
                continue
            source_files = sorted(symbol_files.get(str(edge.get("from")), set()))
            target_files = sorted(symbol_files.get(str(edge.get("to")), set()))
            if not source_files or not target_files:
                continue
            edge_type = str(edge.get("type") or "CALLS")
            key = (source_files[0], target_files[0], edge_type)
            if key in seen:
                continue
            seen.add(key)
            connections.append(ImpactConnection(source=key[0], target=key[1], type=key[2]))
        return connections

    def _validate_target(self, repo_id: str, target: str) -> None:
        if "/" not in target and "\\" not in target:
            return
        try:
            self.repositories.resolve_relative_path(repo_id, target)
        except ValueError:
            raise FacadeError(
                "INVALID_ARGUMENT", "Impact target path must stay in repository"
            ) from None

    def _run_impact_lookup(self, target: str, root: Path, max_depth: int) -> Mapping[str, Any]:
        try:
            raw_value = self.impact_lookup(target, str(root), max_depth)
        except FacadeError:
            raise
        except Exception as exc:
            if self._lookup_signals_index_error(str(exc)):
                raise FacadeError(
                    "INDEX_NOT_READY", "Repository index is not ready", retryable=True
                ) from exc
            raise FacadeError("INTERNAL_ERROR", "Impact analysis failed") from exc

        if not isinstance(raw_value, Mapping):
            raise FacadeError("INTERNAL_ERROR", "Impact analysis returned an invalid result")
        lookup_error = raw_value.get("error")
        if isinstance(lookup_error, str):
            if self._lookup_signals_index_error(lookup_error):
                raise FacadeError(
                    "INDEX_NOT_READY", "Repository index is not ready", retryable=True
                )
            if "репозитор" in lookup_error.lower() or "repository" in lookup_error.lower():
                raise FacadeError("REPO_NOT_FOUND", "Repository is not available")
            raise FacadeError("INTERNAL_ERROR", "Impact analysis failed")
        return raw_value

    def impact(self, request: ImpactRequest) -> ImpactPayload:
        root = self._resolve_repo(request.repo_id)
        self._validate_target(request.repo_id, request.target)
        cache_key = self._cache_key(request.repo_id, root, "impact", request.model_dump())
        if cache_key is not None:
            cached = self.cache.get(cache_key)
            if isinstance(cached, ImpactPayload):
                return cached
        raw_value = self._run_impact_lookup(request.target, root, request.max_depth)

        affected_files = [
            path
            for raw_path in self._string_list(raw_value.get("affected_files"))
            if (path := self._normalize_repo_path(raw_path, root)) is not None
        ]
        suggested_tests = [
            path
            for raw_path in self._string_list(raw_value.get("suggested_tests"))
            if (path := self._normalize_repo_path(raw_path, root)) is not None
        ]
        target_file = None
        raw_matches = raw_value.get("matches")
        if isinstance(raw_matches, list):
            for match in raw_matches:
                if isinstance(match, Mapping):
                    target_file = self._normalize_repo_path(
                        match.get("file") or match.get("path"), root
                    )
                    if target_file is not None:
                        break

        raw_risk = raw_value.get("risk")
        risk = None
        if isinstance(raw_risk, Mapping):
            level = raw_risk.get("level")
            score = raw_risk.get("score")
            if (
                isinstance(level, str)
                and isinstance(score, (int, float))
                and not isinstance(score, bool)
            ):
                risk = ImpactRisk(level=level, score=score)

        result = ImpactResult(
            target=request.target,
            target_file=target_file,
            affected_files=list(dict.fromkeys(affected_files)),
            callers=list(dict.fromkeys(self._string_list(raw_value.get("direct_callers")))),
            callees=list(dict.fromkeys(self._string_list(raw_value.get("direct_callees")))),
            tests=list(dict.fromkeys(suggested_tests)),
            connections=self._normalize_connections(raw_value, root),
            depth=request.max_depth,
            risk=risk,
        )
        payload = ImpactPayload(
            repo=self._repository_metadata(request.repo_id, root),
            result=result,
            ui=UIState(
                focus=UIFocus(path=target_file) if target_file is not None else None,
                highlights=result.affected_files,
                mode="impact",
            ),
        )
        if cache_key is not None:
            self.cache.set(cache_key, payload)
        return payload

    def trace_impact(self, request: ImpactRequest) -> ImpactPayload:
        """Named application action for the browser impact tool."""
        return self.impact(request)

    @staticmethod
    def _snapshot_reference(metadata: Mapping[str, Any]) -> SnapshotReference | None:
        snapshot_id = metadata.get("snapshot_id")
        if not isinstance(snapshot_id, str) or not snapshot_id:
            return None

        def optional_text(key: str, limit: int) -> str | None:
            value = metadata.get(key)
            return value[:limit] if isinstance(value, str) and value else None

        indexed_files = metadata.get("indexed_files")
        return SnapshotReference(
            id=snapshot_id,
            commit=optional_text("commit", 128),
            commit_short=optional_text("commit_short", 24),
            branch=optional_text("branch", 128),
            captured_at_utc=optional_text("captured_at_utc", 64),
            dirty=metadata.get("dirty") if isinstance(metadata.get("dirty"), bool) else None,
            indexed_files=int(indexed_files) if isinstance(indexed_files, (int, float)) else None,
        )

    def _snapshot_records(self, root: Path) -> list[Mapping[str, Any]]:
        try:
            records = self.snapshot_factory(root).list_snapshots(limit=1000)
        except (OSError, TypeError, ValueError):
            return []
        return [record for record in records if isinstance(record, Mapping)]

    def _snapshot_report(self, metadata: Mapping[str, Any], root: Path) -> Mapping[str, Any]:
        raw_dir = metadata.get("snapshot_dir")
        if not isinstance(raw_dir, str) or not raw_dir:
            return {}
        snapshot_dir = Path(raw_dir).expanduser().resolve()
        snapshots_root = (
            self.snapshot_artifacts_dir or (root / ".agents" / "booster")
        ).resolve() / "snapshots"
        if not snapshot_dir.is_relative_to(snapshots_root):
            return {}
        report_path = (snapshot_dir / "scan_report.json").resolve()
        if not report_path.is_relative_to(snapshot_dir) or not report_path.is_file():
            return {}
        try:
            value = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, Mapping) else {}

    def _snapshot_manifest(
        self, metadata: Mapping[str, Any], root: Path
    ) -> dict[str, dict[str, Any]]:
        report = self._snapshot_report(metadata, root)
        raw_manifest = report.get("file_manifest")
        if not isinstance(raw_manifest, Mapping):
            return {}
        manifest: dict[str, dict[str, Any]] = {}
        for raw_path, raw_value in raw_manifest.items():
            if not isinstance(raw_path, str) or not isinstance(raw_value, Mapping):
                continue
            manifest[raw_path] = {
                str(key): value for key, value in raw_value.items() if key != "mtime_ns"
            }
        return manifest

    @staticmethod
    def _manifest_content_hash(value: Mapping[str, Any]) -> str | None:
        candidate = value.get("sha256")
        if not isinstance(candidate, str) or len(candidate) != 64:
            return None
        if any(character not in "0123456789abcdefABCDEF" for character in candidate):
            return None
        return candidate.lower()

    def list_snapshots(self, repo_id: str, limit: int = 20) -> SnapshotListPayload:
        root = self._resolve_repo(repo_id)
        references = [
            reference
            for metadata in self._snapshot_records(root)[: max(1, min(limit, 50))]
            if (reference := self._snapshot_reference(metadata)) is not None
        ]
        return SnapshotListPayload(
            repo=self._repository_metadata(repo_id, root),
            result=SnapshotListResult(snapshots=references),
            ui=UIState(mode="snapshots"),
        )

    def compare_snapshots(self, request: SnapshotCompareRequest) -> SnapshotComparePayload:
        root = self._resolve_repo(request.repo_id)
        cache_key = self._cache_key(request.repo_id, root, "snapshot_compare", request.model_dump())
        if cache_key is not None:
            cached = self.cache.get(cache_key)
            if isinstance(cached, SnapshotComparePayload):
                return cached
        records = {
            metadata.get("snapshot_id"): metadata
            for metadata in self._snapshot_records(root)
            if isinstance(metadata.get("snapshot_id"), str)
        }
        from_metadata = records.get(request.from_id)
        to_metadata = records.get(request.to_id)
        if not isinstance(from_metadata, Mapping) or not isinstance(to_metadata, Mapping):
            raise FacadeError("SNAPSHOT_NOT_FOUND", "Snapshot is not available")
        from_reference = self._snapshot_reference(from_metadata)
        to_reference = self._snapshot_reference(to_metadata)
        if from_reference is None or to_reference is None:
            raise FacadeError("SNAPSHOT_NOT_FOUND", "Snapshot is not available")

        from_manifest = self._snapshot_manifest(from_metadata, root)
        to_manifest = self._snapshot_manifest(to_metadata, root)
        from_paths = set(from_manifest)
        to_paths = set(to_manifest)
        added = sorted(to_paths - from_paths)
        removed = sorted(from_paths - to_paths)
        changed: list[str] = []
        stable: list[str] = []
        unverified: list[str] = []
        for path in sorted(from_paths & to_paths):
            from_hash = self._manifest_content_hash(from_manifest[path])
            to_hash = self._manifest_content_hash(to_manifest[path])
            if from_hash is None or to_hash is None:
                unverified.append(path)
            elif from_hash == to_hash:
                stable.append(path)
            else:
                changed.append(path)
        result = SnapshotCompareResult(
            from_snapshot=from_reference,
            to_snapshot=to_reference,
            added=added,
            removed=removed,
            changed=changed,
            stable=stable,
            unverified=unverified,
            connections=SnapshotConnectionDiff(),
            summary={
                "added": len(added),
                "removed": len(removed),
                "changed": len(changed),
                "stable": len(stable),
                "unverified": len(unverified),
            },
        )
        payload = SnapshotComparePayload(
            repo=self._repository_metadata(request.repo_id, root),
            result=result,
            ui=UIState(
                highlights=added + changed,
                mode="snapshots",
            ),
        )
        if cache_key is not None:
            self.cache.set(cache_key, payload)
        return payload

    def explain_history(self, request: HistoryRequest) -> HistoryPayload:
        root = self._resolve_repo(request.repo_id)
        cache_key = self._cache_key(request.repo_id, root, "history", request.model_dump())
        if cache_key is not None:
            cached = self.cache.get(cache_key)
            if isinstance(cached, HistoryPayload):
                return cached
        path = None
        if request.path:
            try:
                resolved = self.repositories.resolve_relative_path(request.repo_id, request.path)
            except ValueError:
                raise FacadeError(
                    "INVALID_ARGUMENT", "History path must stay in repository"
                ) from None
            path = resolved.relative_to(root).as_posix()

        if self.mode == "demo":
            raw_value = self._demo_history(path, request.symbol, root, request.limit)
        else:
            try:
                raw_value = self.history_lookup(path, request.symbol, str(root), request.limit)
            except FacadeError:
                raise
            except Exception as exc:
                raise FacadeError("INTERNAL_ERROR", "Git history failed") from exc

        if not isinstance(raw_value, Mapping):
            raise FacadeError("INTERNAL_ERROR", "Git history returned an invalid result")
        lookup_error = raw_value.get("error")
        if isinstance(lookup_error, str):
            value = lookup_error.lower()
            if "вне репозитория" in value or "outside" in value:
                raise FacadeError("INVALID_ARGUMENT", "History path must stay in repository")
            if "репозитор" in value or "repository" in value:
                raise FacadeError("REPO_NOT_FOUND", "Repository is not available")
            raise FacadeError("INTERNAL_ERROR", "Git history is unavailable")

        result_path = self._normalize_repo_path(raw_value.get("path"), root)
        if result_path is None:
            result_path = path
        if raw_value.get("path") is not None and result_path is None:
            raise FacadeError("INVALID_ARGUMENT", "History path must stay in repository")

        commits: list[HistoryCommit] = []
        raw_commits = raw_value.get("commits")
        if isinstance(raw_commits, list):
            for item in raw_commits[: request.limit]:
                if not isinstance(item, Mapping):
                    continue
                commit_hash = item.get("hash")
                if not isinstance(commit_hash, str) or not commit_hash:
                    continue
                commits.append(
                    HistoryCommit(
                        hash=commit_hash[:128],
                        short_hash=str(item.get("short_hash") or commit_hash[:12])[:24],
                        author=str(item.get("author") or "")[:256],
                        date=str(item.get("date") or "")[:64],
                        message=str(item.get("message") or "")[:1000],
                    )
                )

        blame: list[HistoryBlame] = []
        raw_blame = raw_value.get("blame")
        if isinstance(raw_blame, list):
            for item in raw_blame[: request.limit]:
                if not isinstance(item, Mapping):
                    continue
                blame_hash = item.get("hash")
                if not isinstance(blame_hash, str) or not blame_hash:
                    continue
                blame.append(
                    HistoryBlame(
                        hash=blame_hash[:128],
                        short_hash=str(item.get("short_hash") or blame_hash[:12])[:24],
                        author=(
                            str(item["author"])[:256] if item.get("author") is not None else None
                        ),
                        date=str(item["date"])[:64] if item.get("date") is not None else None,
                        summary=(
                            str(item["summary"])[:1000] if item.get("summary") is not None else None
                        ),
                        sample_line=(
                            str(item["sample_line"])[:240]
                            if item.get("sample_line") is not None
                            else None
                        ),
                    )
                )

        history_hint = raw_value.get("history_hint")
        if not isinstance(history_hint, str):
            history_hint = "Git history is unavailable"
        result = HistoryResult(
            path=result_path,
            symbol=(
                str(raw_value.get("symbol") or request.symbol)
                if raw_value.get("symbol") or request.symbol
                else None
            ),
            commits=commits,
            blame=blame,
            history_hint=history_hint[:1000],
        )
        payload = HistoryPayload(
            repo=self._repository_metadata(request.repo_id, root),
            result=result,
            ui=UIState(
                focus=UIFocus(path=result_path) if result_path is not None else None,
                highlights=[result_path] if result_path is not None else None,
                mode="history",
            ),
        )
        if cache_key is not None:
            self.cache.set(cache_key, payload)
        return payload

    def show_diagnostics(self, request: DiagnosticsRequest) -> DiagnosticsPayload:
        root = self._resolve_repo(request.repo_id)
        absolute_paths: list[str] = []
        requested_paths: list[str] = []
        for raw_path in request.paths:
            try:
                resolved = self.repositories.resolve_relative_path(request.repo_id, raw_path)
            except ValueError:
                raise FacadeError(
                    "INVALID_ARGUMENT", "Diagnostic path must stay in repository"
                ) from None
            absolute_paths.append(str(resolved))
            requested_paths.append(resolved.relative_to(root).as_posix())

        if self.mode == "demo":
            raw_value = self._demo_diagnostics(requested_paths, root)
        else:
            try:
                raw_value = self.diagnostics_lookup(
                    absolute_paths,
                    str(root),
                    False,
                    False,
                    30,
                )
            except FacadeError:
                raise
            except Exception as exc:
                raise FacadeError("INTERNAL_ERROR", "Diagnostics failed") from exc

        if not isinstance(raw_value, Mapping):
            raise FacadeError("INTERNAL_ERROR", "Diagnostics returned an invalid result")
        lookup_error = raw_value.get("error")
        if isinstance(lookup_error, str):
            if "репозитор" in lookup_error.lower() or "repository" in lookup_error.lower():
                raise FacadeError("REPO_NOT_FOUND", "Repository is not available")
            raise FacadeError("INTERNAL_ERROR", "Diagnostics are unavailable")

        checked_paths: list[str] = []
        raw_checked = raw_value.get("paths_checked")
        if isinstance(raw_checked, list):
            for raw_path in raw_checked:
                path = self._normalize_repo_path(raw_path, root)
                if path is not None:
                    checked_paths.append(path)
        if not checked_paths:
            checked_paths = requested_paths

        findings: list[DiagnosticFinding] = []
        raw_findings = raw_value.get("findings")
        if isinstance(raw_findings, list):
            for item in raw_findings:
                if not isinstance(item, Mapping):
                    continue
                path = self._normalize_repo_path(item.get("file"), root)
                message = item.get("message")
                if path is None or not isinstance(message, str):
                    continue
                line = item.get("line")
                column = item.get("column")
                findings.append(
                    DiagnosticFinding(
                        source=str(item.get("source") or "unknown")[:64],
                        severity=str(item.get("severity") or "unknown")[:32],
                        file=path,
                        line=int(line) if isinstance(line, (int, float)) else None,
                        column=int(column) if isinstance(column, (int, float)) else None,
                        message=message[:2000],
                        rule=str(item["rule"])[:128] if item.get("rule") is not None else None,
                        status=str(item["status"])[:32] if item.get("status") is not None else None,
                    )
                )

        raw_summary = raw_value.get("summary")
        if isinstance(raw_summary, Mapping):
            raw_counts = raw_summary.get("by_severity")
            counts = (
                {
                    str(key): int(value)
                    for key, value in raw_counts.items()
                    if isinstance(value, (int, float))
                }
                if isinstance(raw_counts, Mapping)
                else {}
            )
            total = raw_summary.get("total")
            summary = DiagnosticsSummary(
                status=str(raw_summary.get("status") or "passed"),
                total=int(total) if isinstance(total, (int, float)) else len(findings),
                by_severity=counts,
            )
        else:
            summary = DiagnosticsSummary(
                status="failed" if findings else "passed",
                total=len(findings),
                by_severity={},
            )

        finding_files = list(dict.fromkeys(item.file for item in findings))
        return DiagnosticsPayload(
            repo=self._repository_metadata(request.repo_id, root),
            result=DiagnosticsResult(
                paths_checked=checked_paths,
                summary=summary,
                findings=findings,
            ),
            ui=UIState(highlights=finding_files or None, mode="diagnostics"),
        )

    def find_related_tests(self, request: RelatedTestsRequest) -> RelatedTestsPayload:
        root = self._resolve_repo(request.repo_id)
        self._validate_target(request.repo_id, request.target)
        raw_value = self._run_impact_lookup(request.target, root, 4)

        candidates: dict[str, str] = {}
        raw_suggested = self._string_list(raw_value.get("suggested_tests"))
        for raw_path in raw_suggested:
            path = self._normalize_repo_path(raw_path, root)
            if path is not None:
                candidates[path] = "name"

        raw_imports = raw_value.get("import_hits")
        if isinstance(raw_imports, list):
            for item in raw_imports:
                if not isinstance(item, Mapping):
                    continue
                path = self._normalize_repo_path(item.get("file"), root)
                if path is not None and "test" in path.lower():
                    candidates[path] = "import"

        target_tokens = {
            token.lower()
            for token in request.target.replace("::", ".").replace("/", ".").split(".")
            if token
        }
        relation_order = {"direct": 0, "caller": 1, "import": 2, "name": 3}
        ranked = sorted(
            candidates.items(),
            key=lambda item: (
                relation_order[item[1]],
                0 if any(token in Path(item[0]).stem.lower() for token in target_tokens) else 1,
                item[0],
            ),
        )[: request.limit]
        tests = [RelatedTest(path=path, relation=relation) for path, relation in ranked]
        return RelatedTestsPayload(
            repo=self._repository_metadata(request.repo_id, root),
            result=RelatedTestsResult(target=request.target, tests=tests),
            ui=UIState(
                highlights=[item.path for item in tests] or None,
                mode="tests",
            ),
        )

    @staticmethod
    def _normalize_location(
        match: Mapping[str, Any], root: Path, requested_name: str
    ) -> SymbolLocation | None:
        raw_file = match.get("file") or match.get("path")
        path = BoosterFacade._normalize_repo_path(raw_file, root)
        if path is None:
            return None

        line_value = match.get("line")
        if line_value is None:
            line_value = match.get("start_line")
        if line_value is None:
            start = match.get("start")
            line_value = int(start) + 1 if isinstance(start, (int, float)) else 1
        try:
            line = int(line_value)
        except (TypeError, ValueError):
            line = 1
        name = match.get("name")
        return SymbolLocation(
            name=str(name) if name is not None else requested_name,
            path=path,
            line=max(1, line),
        )

    def _index_not_ready(self, root: Path) -> bool:
        if self._job_is_active(self._state(), root):
            return True
        health = self._health()
        if health.get("repository") in {None, str(root)} and health.get("ready") is False:
            return True
        if health.get("ready") and health.get("repository") in {None, str(root)}:
            return False
        return False

    @staticmethod
    def _lookup_signals_index_error(message: str | None) -> bool:
        if not message:
            return False
        value = message.lower()
        return any(token in value for token in ("стро", "индекс", "indexing", "index is"))

    def focus_symbol(self, request: SymbolFocusRequest) -> FocusSymbolPayload:
        root = self._resolve_repo(request.repo_id)
        matches, lookup_error = self._lookup(request.query)
        for match in matches:
            location = self._normalize_location(match, root, request.query)
            if location is not None:
                metadata = self._repository_metadata(request.repo_id, root)
                return FocusSymbolPayload(
                    repo=metadata,
                    result=FocusSymbolResult(symbol=location),
                    ui=UIState(focus=UIFocus(path=location.path)),
                )

        if self._index_not_ready(root) or self._lookup_signals_index_error(lookup_error):
            raise FacadeError(
                "INDEX_NOT_READY",
                "Repository index is not ready",
                retryable=True,
            )
        raise FacadeError("SYMBOL_NOT_FOUND", "Symbol not found")

    def city_path(self, repo_id: str) -> Path:
        root = self._resolve_repo(repo_id)
        artifact_dir = self.city_artifact_dir or (root / ".agents" / "booster")
        artifact_dir = artifact_dir.resolve()
        if not artifact_dir.is_relative_to(root):
            raise FacadeError("FILE_NOT_FOUND", "Code City artifact is unavailable")
        city_file = (artifact_dir / "code_city.html").resolve()
        if not city_file.is_relative_to(root):
            raise FacadeError("FILE_NOT_FOUND", "Code City artifact is unavailable")
        if not city_file.is_file():
            raise FacadeError("FILE_NOT_FOUND", "Code City artifact is unavailable")
        return city_file
