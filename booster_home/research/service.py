"""Сервис целевых научных инструментов Booster Home."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..delegation import LocalDelegator
from ..memory.artifact_store import redact_sensitive
from .analysis import (
    DEFAULT_EXTRACT,
    compare_run_records,
    metric_series,
    read_rows,
    regime_signature,
    scientific_digest,
)
from .models import (
    CheckpointRecord,
    HypothesisRecord,
    HypothesisStatus,
    ResearchBlock,
    ResearchMode,
)
from .store import CHECKPOINT_EXTENSIONS, ResearchInputError, ResearchStateStore, _token_count

RESEARCH_WORKER_ROLES = {
    "log_analyst",
    "code_search",
    "test_writer",
    "benchmark_reader",
    "diff_reviewer",
    "artifact_indexer",
    "summarizer",
}

DEFAULT_CONTEXT_SOURCES = [
    "current_experiment",
    "relevant_code",
    "last_3_results",
    "active_hypotheses",
    "runtime_contract",
]

DEFAULT_CONTEXT_EXCLUDES = [
    "old_failed_versions",
    "duplicate_logs",
    "binary_artifacts",
    "irrelevant_history",
]

_QUERY_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_]+")


def _words(value: str) -> set[str]:
    return {item.lower() for item in _QUERY_WORD_RE.findall(value) if len(item) > 1}


def _json_text(value: Any, *, max_chars: int = 30_000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... [truncated] ..."


def _redact(value: str) -> str:
    return redact_sensitive(value)[0]


def _redact_value(value: Any) -> Any:
    """Рекурсивно redacts strings перед возвратом repository-derived data."""
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, dict):
        return {key: _redact_value(item) for key, item in value.items()}
    return value


def _relative(store: ResearchStateStore, path: Path) -> str:
    return path.resolve().relative_to(store.root).as_posix()


def _record_tokens(value: str) -> int:
    return _token_count(value)


class ResearchService:
    """Оркестрирует research tools поверх локальных файлов и shared Booster graph."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        indexer: Any | None = None,
        cognitive_runtime: Any | None = None,
        delegator: LocalDelegator | None = None,
        settings: Any | None = None,
    ) -> None:
        self.root = (root or Path.cwd()).expanduser().resolve()
        self.indexer = indexer
        self.cognitive_runtime = cognitive_runtime
        self.delegator = delegator
        self.settings = settings
        self._stores: dict[str, ResearchStateStore] = {}

    def _store(self, root: str | Path | None = None) -> ResearchStateStore:
        requested = self.root if root is None else Path(root).expanduser().resolve()
        key = str(requested)
        store = self._stores.get(key)
        if store is None:
            store = ResearchStateStore(requested)
            self._stores[key] = store
        return store

    @staticmethod
    def _priority(path: Path) -> int:
        name = path.name.lower()
        if name == "research_state.json":
            return 0
        if "report" in name or "metrics" in name:
            return 1
        if path.suffix.lower() in CHECKPOINT_EXTENSIONS:
            return 1
        if path.suffix.lower() in {".md", ".toml", ".yaml", ".yml"}:
            return 2
        if path.suffix.lower() in {".py", ".rs", ".ts", ".tsx", ".js", ".jsx"}:
            return 3
        return 4

    def project_snapshot(
        self,
        root: str | None = None,
        include: list[str] | None = None,
        max_tokens: int = 12_000,
        mode: str = "semantic",
    ) -> dict[str, Any]:
        """Собирает компактный снимок проекта и никогда не читает checkpoint body."""
        if not 256 <= max_tokens <= 100_000:
            raise ResearchInputError("max_tokens должен находиться в диапазоне 256..100000")
        if mode not in {"semantic", "deterministic"}:
            raise ResearchInputError("mode должен быть semantic или deterministic")
        store = self._store(root)
        files: list[dict[str, Any]] = []
        checkpoints: list[dict[str, Any]] = []
        warnings: list[str] = []
        for path, metadata_only in store.iter_files(include):
            relative = _relative(store, path)
            is_checkpoint = store.is_checkpoint(path) or metadata_only
            if is_checkpoint:
                try:
                    record = store.checkpoint_metadata(path).model_dump(mode="json")
                except ResearchInputError as exc:
                    warnings.append(str(exc))
                    continue
                checkpoints.append(record)
                files.append(
                    {
                        "path": relative,
                        "kind": "checkpoint_metadata",
                        "size_bytes": record["size_bytes"],
                        "metadata": record,
                        "binary_content_included": False,
                        "token_count": _record_tokens(_json_text(record)),
                    }
                )
                continue
            try:
                text, truncated = store.read_text(path)
            except (OSError, UnicodeError) as exc:
                warnings.append(f"не удалось прочитать {relative}: {type(exc).__name__}")
                continue
            if "\x00" in text[:4096]:
                warnings.append(f"binary content excluded: {relative}")
                continue
            text = _redact(text)
            files.append(
                {
                    "path": relative,
                    "kind": "text",
                    "size_bytes": path.stat().st_size,
                    "content": text,
                    "truncated": truncated,
                    "binary_content_included": False,
                    "token_count": _record_tokens(text),
                }
            )

        files.sort(key=lambda item: (self._priority(Path(item["path"])), item["path"]))
        budget_chars = max_tokens * 4
        used_chars = 0
        selected: list[dict[str, Any]] = []
        for item in files:
            value = dict(item)
            metadata = value.get("metadata")
            base = _json_text({key: value[key] for key in value if key not in {"content"}})
            available = max(0, budget_chars - used_chars - len(base))
            if "content" in value:
                content = value["content"]
                if available <= 0:
                    value["content"] = ""
                elif len(content) > available:
                    value["content"] = content[:available] + "\n... [context budget] ..."
                value["token_count"] = _record_tokens(value.get("content", ""))
            selected.append(value)
            used_chars += len(_json_text(value))
            if used_chars >= budget_chars and metadata is None:
                break

        semantic_hits: list[dict[str, Any]] = []
        if mode == "semantic" and self.indexer is not None:
            try:
                hits = self.indexer.hybrid_search(
                    "current experiment metrics baseline hypothesis runtime", k=8
                )
                for hit in hits:
                    if isinstance(hit, dict):
                        semantic_hits.append(
                            {
                                "file": hit.get("file"),
                                "score": hit.get("score"),
                                "preview": _redact(str(hit.get("chunk", hit.get("content", ""))))[
                                    :800
                                ],
                            }
                        )
            except Exception as exc:
                warnings.append(f"semantic snapshot retrieval unavailable: {type(exc).__name__}")
        return _redact_value(
            {
                "root": str(store.root),
                "mode": mode,
                "max_tokens": max_tokens,
                "files": selected,
                "checkpoints": checkpoints,
                "semantic_hits": semantic_hits,
                "estimated_tokens": _record_tokens(_json_text(selected))
                + _record_tokens(_json_text(semantic_hits)),
                "binary_content_included": False,
                "warnings": warnings,
            }
        )

    def _memory_context(self, store: ResearchStateStore) -> tuple[str, list[str]]:
        pieces: list[str] = []
        sources: list[str] = []
        keywords = {"baseline", "best", "hypothesis", "confound", "assumption", "next"}
        for path in store.memory_files():
            try:
                text, _ = store.read_text(path, max_bytes=32_000)
            except OSError:
                continue
            relevant = [
                line for line in text.splitlines() if keywords.intersection(_words(line.lower()))
            ]
            if relevant:
                pieces.extend(relevant[:80])
                sources.append(_relative(store, path))
        return "\n".join(pieces), sources

    def _metric_run_summaries(self, store: ResearchStateStore, limit: int) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for path in store.metric_files():
            try:
                rows, truncated, invalid = read_rows(path)
            except (OSError, UnicodeError):
                continue
            if not rows:
                continue
            series = metric_series(rows)
            summaries.append(
                {
                    "run": path.stem,
                    "path": _relative(store, path),
                    "last": rows[-1],
                    "metrics": {key: values[-1] for key, values in series.items()},
                    "eval_regime": regime_signature(rows),
                    "truncated": truncated,
                    "invalid_lines": invalid,
                }
            )
        return summaries[-max(1, min(limit, 50)) :]

    def experiment_state(
        self,
        project: str | None = None,
        max_tokens: int = 4_000,
        include_history: int = 6,
    ) -> dict[str, Any]:
        """Возвращает научное состояние из файлов, а не из conversation history."""
        if not 256 <= max_tokens <= 100_000:
            raise ResearchInputError("max_tokens должен находиться в диапазоне 256..100000")
        store = self._store(project)
        state, warnings = store.load_state()
        hypotheses = self._hypotheses(state)
        history = state.get("history", state.get("experiments", []))
        if not isinstance(history, list):
            history = []
        summaries = self._metric_run_summaries(store, include_history)
        if not history:
            history = summaries
        active = state.get("active_hypothesis")
        if active is None:
            active = next(
                (
                    item.model_dump(mode="json")
                    for item in hypotheses
                    if item.status == HypothesisStatus.TESTING
                ),
                next(
                    (
                        item.model_dump(mode="json")
                        for item in hypotheses
                        if item.status == HypothesisStatus.PROPOSED
                    ),
                    None,
                ),
            )
        last_failed = state.get("last_failed_hypothesis")
        if last_failed is None:
            last_failed = next(
                (
                    item.model_dump(mode="json")
                    for item in reversed(hypotheses)
                    if item.status == HypothesisStatus.REJECTED
                ),
                None,
            )
        memory_context, memory_sources = self._memory_context(store)
        result = {
            "project": state.get("project", store.root.name),
            "root": str(store.root),
            "current_baseline": state.get("current_baseline"),
            "current_best_result": state.get("current_best_result"),
            "last_failed_hypothesis": last_failed,
            "active_hypothesis": active,
            "known_confounds": state.get("known_confounds", state.get("confounds", [])),
            "frozen_assumptions": state.get("frozen_assumptions", state.get("assumptions", [])),
            "next_candidate_experiments": state.get("next_candidate_experiments", []),
            "hypotheses": [item.model_dump(mode="json") for item in hypotheses],
            "history": history[-max(1, min(include_history, 50)) :],
            "metrics": summaries,
            "memory_context": _redact(memory_context),
            "memory_sources": memory_sources,
            "state_sources": [str(store.state_path())] if state else [],
            "warnings": warnings,
        }
        serialized = _json_text(result)
        if _record_tokens(serialized) > max_tokens:
            result["history"] = result["history"][-2:]
            result["metrics"] = result["metrics"][-2:]
            result["memory_context"] = result["memory_context"][: max_tokens * 2]
            result["warnings"].append("experiment state truncated to max_tokens")
        result["estimated_tokens"] = _record_tokens(_json_text(result))
        return _redact_value(result)

    def _resolve_reference(self, store: ResearchStateStore, value: str) -> Path:
        try:
            return store.resolve_path(value)
        except ResearchInputError:
            needle = value.lower()
            candidates = [
                path
                for path, _ in store.iter_files(["**/*"])
                if needle in path.name.lower() or needle in path.as_posix().lower()
            ]
            if not candidates:
                raise
            candidates.sort(key=lambda path: ("metrics" not in path.name.lower(), path.name))
            return candidates[0]

    def artifact_lookup(
        self,
        query: str,
        types: list[str] | None = None,
        top_k: int = 8,
        root: str | None = None,
    ) -> dict[str, Any]:
        """Ищет артефакты lexical/semantic-like способом без чтения binary body."""
        if not query.strip():
            raise ResearchInputError("query не может быть пустым")
        if not 1 <= top_k <= 50:
            raise ResearchInputError("top_k должен находиться в диапазоне 1..50")
        store = self._store(root)
        requested = {item.lower().lstrip(".") for item in (types or [])}
        query_words = _words(query)
        matches: list[dict[str, Any]] = []
        for path, _ in store.iter_files(["**/*"]):
            extension = path.suffix.lower().lstrip(".")
            if requested and extension not in requested:
                continue
            relative = _relative(store, path)
            metadata_only = store.is_checkpoint(path)
            preview = ""
            metadata: dict[str, Any] | None = None
            if metadata_only:
                metadata = _redact_value(store.checkpoint_metadata(path).model_dump(mode="json"))
                haystack = f"{relative} {_json_text(metadata)}".lower()
            else:
                try:
                    preview, _ = store.read_text(path, max_bytes=12_000)
                except (OSError, UnicodeError):
                    continue
                if "\x00" in preview[:4096]:
                    continue
                preview = _redact(preview)
                haystack = f"{relative} {preview}".lower()
            content_words = _words(haystack)
            overlap = len(query_words.intersection(content_words))
            exact = sum(1 for word in query_words if word in relative.lower())
            if overlap == 0 and exact == 0:
                continue
            score = exact * 3.0 + overlap / max(1, len(query_words))
            matches.append(
                {
                    "path": relative,
                    "type": extension or "file",
                    "score": round(score, 4),
                    "binary_content_included": False,
                    "preview": None if metadata_only else preview[:800],
                    "metadata": metadata,
                }
            )
        if self.indexer is not None:
            try:
                semantic_hits = self.indexer.hybrid_search(query, k=top_k)
            except Exception:
                semantic_hits = []
            known_paths = {item["path"] for item in matches}
            for hit in semantic_hits:
                if not isinstance(hit, dict) or not hit.get("file"):
                    continue
                try:
                    hit_path = store.resolve_path(str(hit["file"]))
                except ResearchInputError:
                    continue
                relative = _relative(store, hit_path)
                extension = hit_path.suffix.lower().lstrip(".")
                if requested and extension not in requested or relative in known_paths:
                    continue
                matches.append(
                    {
                        "path": relative,
                        "type": extension or "file",
                        "score": round(float(hit.get("score", 0.0)), 4),
                        "binary_content_included": False,
                        "preview": _redact(str(hit.get("chunk", "")))[:800],
                        "metadata": None,
                    }
                )
        matches.sort(key=lambda item: (-item["score"], item["path"]))
        return _redact_value(
            {
                "root": str(store.root),
                "query": query,
                "top_k": top_k,
                "results": matches[:top_k],
                "binary_content_included": False,
            }
        )

    def log_digest(
        self,
        path: str,
        extract: list[str] | None = None,
        compare_to: str | None = None,
        root: str | None = None,
    ) -> dict[str, Any]:
        """Формирует OBSERVED/INCREASED/... digest из JSONL/JSON metrics."""
        store = self._store(root)
        source = self._resolve_reference(store, path)
        rows, truncated, invalid = read_rows(source)
        baseline_rows: list[dict[str, Any]] | None = None
        baseline_path: Path | None = None
        if compare_to:
            baseline_path = self._resolve_reference(store, compare_to)
            baseline_rows, _, _ = read_rows(baseline_path)
        digest = scientific_digest(
            rows,
            extract or DEFAULT_EXTRACT,
            invalid_lines=invalid,
            truncated=truncated,
            compare_rows=baseline_rows,
        )
        digest.update(
            {
                "path": _relative(store, source),
                "compare_to": _relative(store, baseline_path) if baseline_path else None,
                "binary_content_included": False,
            }
        )
        return digest

    def compare_runs(
        self,
        runs: list[str],
        metrics: list[str],
        normalize_eval_regime: bool = True,
        root: str | None = None,
    ) -> dict[str, Any]:
        """Сравнивает последние числовые значения только при совместимом eval regime."""
        if len(runs) < 2:
            raise ResearchInputError("для compare_runs нужны минимум два run")
        if not metrics:
            raise ResearchInputError("metrics не может быть пустым")
        store = self._store(root)
        records: list[dict[str, Any]] = []
        for run in runs[:20]:
            path = self._resolve_reference(store, run)
            rows, truncated, invalid = read_rows(path)
            records.append(
                {
                    "run": run,
                    "path": _relative(store, path),
                    "series": metric_series(rows),
                    "regime": regime_signature(rows),
                    "rows": len(rows),
                    "truncated": truncated,
                    "invalid_lines": invalid,
                }
            )
        result = compare_run_records(records, metrics, normalize_eval_regime=normalize_eval_regime)
        result.update({"root": str(store.root), "runs": records, "binary_content_included": False})
        return result

    @staticmethod
    def _hypotheses(state: dict[str, Any]) -> list[HypothesisRecord]:
        raw = state.get("hypotheses", [])
        if isinstance(raw, dict):
            raw = list(raw.values())
        result: list[HypothesisRecord] = []
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict) or not item.get("hypothesis"):
                continue
            try:
                result.append(HypothesisRecord.model_validate(item))
            except ValueError:
                continue
        return result

    def hypothesis_register(
        self,
        action: str = "record",
        hypothesis: str | None = None,
        status: str = "proposed",
        evidence_for: list[str] | None = None,
        evidence_against: list[str] | None = None,
        confounds: list[str] | None = None,
        confidence: float = 0.0,
        hypothesis_id: str | None = None,
        project: str | None = None,
        control_arms: list[str] | None = None,
        independent_variable: str | None = None,
        dependent_metrics: list[str] | None = None,
        pass_criteria: list[str] | None = None,
        fail_criteria: list[str] | None = None,
        required_artifacts: list[str] | None = None,
    ) -> dict[str, Any]:
        """Регистрирует и перечисляет scientific memory без чата."""
        if action not in {"record", "update", "list", "get"}:
            raise ResearchInputError("action должен быть record, update, list или get")
        store = self._store(project)
        state, warnings = store.load_state()
        records = self._hypotheses(state)
        if action == "list":
            return {
                "project": str(store.root),
                "hypotheses": [item.model_dump(mode="json") for item in records],
                "warnings": warnings,
            }
        if action == "get":
            selected = next((item for item in records if item.id == hypothesis_id), None)
            if selected is None:
                raise ResearchInputError(f"гипотеза не найдена: {hypothesis_id}")
            return {
                "project": str(store.root),
                "hypothesis": selected.model_dump(mode="json"),
                "warnings": warnings,
            }
        if action == "update" and not hypothesis_id:
            raise ResearchInputError("hypothesis_id обязателен для update")
        if action == "record" and not hypothesis:
            raise ResearchInputError("hypothesis обязателен для record")
        now = datetime.now(timezone.utc).isoformat()
        if action == "update":
            selected = next((item for item in records if item.id == hypothesis_id), None)
            if selected is None:
                raise ResearchInputError(f"гипотеза не найдена: {hypothesis_id}")
            payload = selected.model_dump(mode="json")
            updates = {
                "hypothesis": hypothesis,
                "status": (
                    status
                    if status != "proposed" or selected.status == HypothesisStatus.PROPOSED
                    else None
                ),
                "evidence_for": evidence_for,
                "evidence_against": evidence_against,
                "confounds": confounds,
                "confidence": confidence if confidence != 0.0 else None,
                "control_arms": control_arms,
                "independent_variable": independent_variable,
                "dependent_metrics": dependent_metrics,
                "pass_criteria": pass_criteria,
                "fail_criteria": fail_criteria,
                "required_artifacts": required_artifacts,
            }
            payload.update({key: value for key, value in updates.items() if value is not None})
            payload["updated_at"] = now
            selected = HypothesisRecord.model_validate(payload)
            records = [selected if item.id == selected.id else item for item in records]
        else:
            if status not in {item.value for item in HypothesisStatus}:
                raise ResearchInputError(f"недопустимый hypothesis status: {status}")
            next_number = 1
            for item in records:
                match = re.fullmatch(r"H-(\d+)", item.id)
                if match:
                    next_number = max(next_number, int(match.group(1)) + 1)
            selected = HypothesisRecord(
                id=hypothesis_id or f"H-{next_number:03d}",
                hypothesis=hypothesis or "",
                status=status,
                evidence_for=evidence_for or [],
                evidence_against=evidence_against or [],
                confounds=confounds or [],
                confidence=confidence,
                control_arms=control_arms or [],
                independent_variable=independent_variable,
                dependent_metrics=dependent_metrics or [],
                pass_criteria=pass_criteria or [],
                fail_criteria=fail_criteria or [],
                required_artifacts=required_artifacts or [],
                updated_at=now,
            )
            records.append(selected)
        updated = dict(state)
        updated["hypotheses"] = [item.model_dump(mode="json") for item in records]
        updated["active_hypothesis"] = (
            selected.model_dump(mode="json")
            if selected.status in {HypothesisStatus.TESTING, HypothesisStatus.PROPOSED}
            else state.get("active_hypothesis")
        )
        store.save_state(updated)
        return {
            "project": str(store.root),
            "hypothesis": selected.model_dump(mode="json"),
            "count": len(records),
            "warnings": warnings,
        }

    def next_experiment(
        self,
        hypothesis_id: str,
        constraints: dict[str, Any] | None = None,
        project: str | None = None,
    ) -> dict[str, Any]:
        """Собирает candidate experiment из уже зарегистрированной гипотезы."""
        store = self._store(project)
        state, warnings = store.load_state()
        selected = next(
            (item for item in self._hypotheses(state) if item.id == hypothesis_id),
            None,
        )
        if selected is None:
            raise ResearchInputError(f"гипотеза не найдена: {hypothesis_id}")
        limits = dict(constraints or {})
        candidate = {
            "id": f"X-{selected.id}",
            "source_hypothesis": selected.model_dump(mode="json"),
            "goal": f"Проверить гипотезу: {selected.hypothesis}",
            "control_arms": selected.control_arms or ["baseline", "candidate"],
            "independent_variable": selected.independent_variable
            or "intervention described by the registered hypothesis",
            "dependent_metrics": selected.dependent_metrics
            or ["CE", "heldout", "entropy", "state_drift", "settling", "step_s"],
            "confounds": sorted(set(selected.confounds)),
            "pass_criteria": selected.pass_criteria
            or ["candidate improves the registered dependent metric under the same eval regime"],
            "fail_criteria": selected.fail_criteria
            or ["no improvement, regime mismatch, or collapse signal"],
            "required_artifacts": selected.required_artifacts
            or ["metrics.jsonl", "run report", "checkpoint metadata"],
            "constraints": limits,
            "derived_defaults": not bool(
                selected.control_arms
                and selected.independent_variable
                and selected.dependent_metrics
                and selected.pass_criteria
                and selected.fail_criteria
                and selected.required_artifacts
            ),
        }
        candidates = state.get("next_candidate_experiments", [])
        if not isinstance(candidates, list):
            candidates = []
        candidates = [item for item in candidates if item.get("id") != candidate["id"]]
        candidates.append(candidate)
        state["next_candidate_experiments"] = candidates[-50:]
        store.save_state(state)
        return {"project": str(store.root), **candidate, "warnings": warnings}

    def context_pack(
        self,
        task: str,
        budget_tokens: int = 16_000,
        sources: list[str] | None = None,
        exclude: list[str] | None = None,
        mode: str = "research",
        project: str | None = None,
    ) -> dict[str, Any]:
        """Собирает L0..L4 context layers с bounded provenance."""
        if not task.strip():
            raise ResearchInputError("task не может быть пустым")
        if not 256 <= budget_tokens <= 100_000:
            raise ResearchInputError("budget_tokens должен находиться в диапазоне 256..100000")
        try:
            selected_mode = ResearchMode(mode)
        except ValueError as exc:
            raise ResearchInputError(f"неподдерживаемый context mode: {mode}") from exc
        source_names = sources or DEFAULT_CONTEXT_SOURCES
        excluded = set(exclude or DEFAULT_CONTEXT_EXCLUDES)
        store = self._store(project)
        blocks: list[ResearchBlock] = []
        warnings: list[str] = []
        seen_content: list[set[str]] = []

        def add_block(
            layer: str,
            source: str,
            content: str,
            priority: int,
            *,
            untrusted: bool = True,
        ) -> None:
            if not content.strip() or source in excluded:
                return
            normalized_words = _words(content)
            if "duplicate_logs" in excluded and normalized_words:
                for previous in seen_content:
                    similarity = len(normalized_words & previous) / max(
                        1, len(normalized_words | previous)
                    )
                    if similarity >= 0.92:
                        return
            seen_content.append(normalized_words)
            blocks.append(
                ResearchBlock(
                    id=f"{layer.lower()}_{len(blocks) + 1}",
                    layer=layer,
                    source=source,
                    content=_redact(content),
                    priority=priority,
                    untrusted=untrusted,
                    token_count=_record_tokens(content),
                )
            )

        add_block("L0", "current_task", task, 0, untrusted=False)
        state = self.experiment_state(project=project, max_tokens=min(4000, budget_tokens))
        if "current_experiment" in source_names:
            add_block("L1", "current_experiment", _json_text(state), 1)
        if "active_hypotheses" in source_names:
            active = [
                item for item in state["hypotheses"] if item["status"] in {"testing", "proposed"}
            ]
            add_block("L1", "active_hypotheses", _json_text(active), 1)
        if "last_3_results" in source_names and "irrelevant_history" not in excluded:
            add_block("L2", "last_3_results", _json_text(state["history"][-3:]), 2)
        if "relevant_code" in source_names:
            code_blocks: list[str] = []
            if self.indexer is not None:
                try:
                    hits = self.indexer.hybrid_search(task, k=8)
                    for hit in hits:
                        if isinstance(hit, dict):
                            path = hit.get("file", "unknown")
                            chunk = _redact(str(hit.get("chunk", hit.get("content", ""))))[:2500]
                            code_blocks.append(f"FILE: {path}\n{chunk}")
                except Exception as exc:
                    warnings.append(f"code retrieval unavailable: {type(exc).__name__}")
            if not code_blocks:
                lookup = self.artifact_lookup(
                    task, ["py", "rs", "ts", "tsx", "js", "jsx"], 4, project
                )
                code_blocks = [
                    f"FILE: {item['path']}\n{item.get('preview') or ''}"
                    for item in lookup["results"]
                ]
            add_block("L2", "relevant_code", "\n\n".join(code_blocks), 2)
        if "runtime_contract" in source_names:
            for candidate in (store.root / "SPEC.md", store.root / "README.md"):
                if candidate.is_file():
                    text, _ = store.read_text(candidate, max_bytes=8_000)
                    add_block("L3", "runtime_contract", text, 3)
                    break
        if "old_failed_versions" not in excluded and "irrelevant_history" not in excluded:
            add_block("L4", "archive", _json_text(state["history"]), 4)

        blocks.sort(key=lambda item: (item.priority, item.layer, item.id))
        remaining = budget_tokens
        selected_blocks: list[ResearchBlock] = []

        def block_cost(block: ResearchBlock) -> int:
            header = f"[{block.layer} {block.source}]\n"
            return block.token_count + _record_tokens(header)

        for block in blocks:
            cost = block_cost(block)
            if cost <= remaining:
                selected_blocks.append(block)
                remaining -= cost
                continue
            if block.layer == "L0" and remaining > 0:
                header_tokens = _record_tokens(f"[{block.layer} {block.source}]\n")
                content = block.content[: max(0, (remaining - header_tokens) * 4)]
                selected_blocks.append(
                    block.model_copy(
                        update={"content": content, "token_count": _record_tokens(content)}
                    )
                )
                remaining = 0
            elif block.priority <= 1:
                warnings.append(f"protected context truncated: {block.source}")
        context_text = "\n\n".join(
            f"[{block.layer} {block.source}]\n{block.content}" for block in selected_blocks
        )
        return _redact_value(
            {
                "task": task,
                "mode": selected_mode.value,
                "budget_tokens": budget_tokens,
                "tokens": _record_tokens(context_text),
                "layers": [block.model_dump(mode="json") for block in selected_blocks],
                "context": context_text,
                "sources": sorted({block.source for block in selected_blocks}),
                "excluded": sorted(excluded),
                "warnings": warnings,
                "binary_content_included": False,
            }
        )

    async def worker_delegate(
        self,
        role: str,
        model: str | None,
        task: str,
        context_budget: int = 8_000,
        output_budget: int = 1_500,
        context: str = "",
        project: str | None = None,
    ) -> dict[str, Any]:
        """Делегирует только одну из заранее разрешённых ролей."""
        if role not in RESEARCH_WORKER_ROLES:
            return {
                "status": "rejected",
                "role": role,
                "error": "research worker role is not allowed",
                "allowed_roles": sorted(RESEARCH_WORKER_ROLES),
            }
        if not 256 <= context_budget <= 100_000 or not 1 <= output_budget <= 8_192:
            raise ResearchInputError("worker budgets выходят за допустимый диапазон")
        if self.delegator is None:
            return {"status": "unavailable", "role": role, "error": "worker pool не подключён"}
        bounded_context = context[: context_budget * 4]
        result = await self.delegator.delegate_local(
            task,
            role=role,
            model=model,
            max_output_tokens=output_budget,
            repo=str(self._store(project).root),
            context=bounded_context,
        )
        return _redact_value(
            {
                "role": role,
                "model": model,
                "context_budget": context_budget,
                "output_budget": output_budget,
                "result": result,
            }
        )

    def checkpoint_registry(
        self,
        action: str,
        path: str | None = None,
        experiment: str | None = None,
        parent: str | None = None,
        step: int | None = None,
        status: str | None = None,
        keep: bool | None = None,
        branch: str | None = None,
        criteria: dict[str, Any] | None = None,
        project: str | None = None,
    ) -> dict[str, Any]:
        """Регистрирует checkpoint metadata и формирует KEEP/delete candidates."""
        if action not in {"register", "find", "remove"}:
            raise ResearchInputError("checkpoint action должен быть register, find или remove")
        store = self._store(project)
        state, warnings = store.load_state()
        raw_records = state.get("checkpoints", [])
        records = [
            CheckpointRecord.model_validate(item).model_dump(mode="json")
            for item in raw_records
            if isinstance(item, dict) and item.get("path")
        ]
        if action == "register":
            if not path:
                raise ResearchInputError("path обязателен для checkpoint register")
            target = store.resolve_path(path)
            if not target.is_file():
                raise ResearchInputError(f"checkpoint не является файлом: {target}")
            record = store.checkpoint_metadata(target).model_dump(mode="json")
            record.update(
                {
                    "experiment": experiment or record.get("experiment"),
                    "parent_experiment": parent or record.get("parent_experiment"),
                    "step": step if step is not None else record.get("step"),
                    "status": status or record.get("status"),
                    "keep": keep if keep is not None else record.get("keep"),
                    "branch": branch or record.get("branch"),
                }
            )
            records = [item for item in records if item.get("path") != record["path"]]
            records.append(record)
            state["checkpoints"] = records
            store.save_state(state)
            return {
                "action": action,
                "checkpoint": record,
                "count": len(records),
                "warnings": warnings,
            }
        if action == "remove":
            if not path:
                raise ResearchInputError("path обязателен для checkpoint remove")
            target = store.resolve_path(path, must_exist=False)
            relative = target.relative_to(store.root).as_posix()
            records = [item for item in records if item.get("path") != relative]
            state["checkpoints"] = records
            store.save_state(state)
        selected = []
        requested = criteria or {}
        for item in records:
            if all(item.get(key) == value for key, value in requested.items()):
                selected.append(item)
        keep_records = [
            item
            for item in selected
            if item.get("keep") is True or item.get("status") in {"baseline", "kept"}
        ]
        delete_candidates = [
            item
            for item in selected
            if item not in keep_records
            and item.get("keep") is not True
            and item.get("status") in {"failed", "discard", "intermediate", None}
        ]
        return {
            "action": action,
            "criteria": requested,
            "KEEP": keep_records,
            "DELETE_CANDIDATES": delete_candidates,
            "checkpoints": selected,
            "warnings": warnings,
        }

    def lightning_trace(
        self,
        prompt: str,
        target_mode: str = "next_token",
        checkpoint: str | None = None,
        trace: list[str] | None = None,
        human_labels: bool = True,
        project: str | None = None,
    ) -> dict[str, Any]:
        """Читает существующий LightningField trace, не симулируя отсутствующие данные."""
        store = self._store(project)
        checkpoint_path: Path | None = None
        checkpoint_metadata: dict[str, Any] | None = None
        trace_path: Path | None = None
        if checkpoint:
            checkpoint_path = self._resolve_reference(store, checkpoint)
            if store.is_checkpoint(checkpoint_path):
                checkpoint_metadata = store.checkpoint_metadata(checkpoint_path).model_dump(
                    mode="json"
                )
                candidates = [
                    checkpoint_path.with_suffix(checkpoint_path.suffix + ".trace.jsonl"),
                    checkpoint_path.with_name(f"{checkpoint_path.stem}_trace.jsonl"),
                    checkpoint_path.with_name(f"{checkpoint_path.stem}.trace.jsonl"),
                ]
                trace_path = next((item for item in candidates if item.is_file()), None)
            elif checkpoint_path.suffix.lower() in {".json", ".jsonl"}:
                trace_path = checkpoint_path
        if trace_path is None and checkpoint is None:
            candidates = [
                path for path, _ in store.iter_files(["**/*trace*.jsonl", "**/*trace*.json"])
            ]
            trace_path = candidates[0] if candidates else None
        records: list[dict[str, Any]] = []
        warnings: list[str] = []
        if trace_path is not None:
            rows, truncated, invalid = read_rows(trace_path)
            requested = set(
                trace or ["frontier", "energy", "state", "route", "candidate_targets", "settling"]
            )
            fields = {
                "token",
                "target",
                "step",
                "selected_nodes",
                "candidate_nodes",
                "energy",
                "target_rank",
                "route_regret",
                "state_drift",
                "semantic_labels",
            }
            for row in rows:
                record = {key: row.get(key) for key in fields if key in row}
                record.setdefault("step", row.get("global_step", row.get("iteration")))
                if human_labels:
                    labels = row.get("semantic_labels", row.get("labels"))
                    if labels is not None:
                        record["semantic_labels"] = (
                            labels if isinstance(labels, list) else [str(labels)]
                        )
                record["trace_fields"] = sorted(requested.intersection(set(row)))
                records.append(record)
            if truncated:
                warnings.append("trace file was bounded before parsing")
            if invalid:
                warnings.append(f"invalid trace rows: {invalid}")
        else:
            warnings.append("trace data not found; binary checkpoint body was not read")
        return _redact_value(
            {
                "status": "ok" if records else "trace_unavailable",
                "prompt": _redact(prompt),
                "target_mode": target_mode,
                "checkpoint": checkpoint,
                "checkpoint_metadata": checkpoint_metadata,
                "trace_path": _relative(store, trace_path) if trace_path else None,
                "records": records,
                "human_labels": human_labels,
                "warnings": warnings,
                "binary_content_included": False,
            }
        )


__all__ = [
    "DEFAULT_CONTEXT_EXCLUDES",
    "DEFAULT_CONTEXT_SOURCES",
    "RESEARCH_WORKER_ROLES",
    "ResearchService",
]
