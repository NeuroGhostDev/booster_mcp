"""Cognitive Runtime tools for Booster MCP.

Модуль собирает AST-граф, git history, project memory и diagnostics в один
headless-слой восприятия для coding agents.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, cast

from repository_scanner import RepositoryScanner

SOURCE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".rs", ".go", ".java"}
PYTHON_EXTENSIONS = {".py"}
TYPESCRIPT_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx"}
RUST_EXTENSIONS = {".rs"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _last_identifier(value: str) -> str:
    parts = re.split(r"[.:]+|::", value)
    return next((part for part in reversed(parts) if part), value)


def _callee_matches(callee: str, target_names: set[str]) -> bool:
    if callee in target_names:
        return True
    last = _last_identifier(callee)
    return last in target_names or any(callee.endswith(f".{name}") for name in target_names)


class CognitiveRuntime:
    """Оркестратор знаний проекта поверх существующего RepoIndexer."""

    def __init__(self, indexer: Any, repos: list[str]):
        self.indexer = indexer
        self.repos = repos
        self._memory_lock = threading.RLock()

    def _resolve_repo(self, repo: Optional[str] = None) -> Path:
        if repo:
            repo_path = Path(repo).expanduser().resolve()
        elif self.repos:
            repo_path = Path(self.repos[0]).expanduser().resolve()
        else:
            raise ValueError("Нет добавленных репозиториев. Используйте add_repo().")

        if not repo_path.exists() or not repo_path.is_dir():
            raise ValueError(f"Репозиторий не найден: {repo_path}")
        return repo_path

    def _memory_file(self, repo_path: Path) -> Path:
        path = repo_path / ".agents" / "booster" / "memory.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _load_memory(self, repo_path: Path) -> dict[str, Any]:
        path = self._memory_file(repo_path)
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"project memory повреждена: {path}") from exc
        if not isinstance(value, dict):
            raise RuntimeError(f"project memory должна быть JSON object: {path}")
        return value

    def _save_memory(self, repo_path: Path, memory: dict[str, Any]) -> None:
        path = self._memory_file(repo_path)
        payload = json.dumps(memory, ensure_ascii=False, indent=2).encode("utf-8")
        with self._memory_lock:
            fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            except Exception:
                Path(temporary).unlink(missing_ok=True)
                raise

    def _inside_repo(self, path: Path, repo_path: Path) -> bool:
        try:
            path.resolve().relative_to(repo_path)
            return True
        except ValueError:
            return False

    def _relative(self, path: Path, repo_path: Path) -> str:
        try:
            return path.resolve().relative_to(repo_path).as_posix()
        except ValueError:
            return str(path)

    def _resolve_paths(self, paths: Optional[list[str]], repo_path: Path) -> list[Path]:
        if not paths:
            indexed_paths: list[Path] = []
            symbols_by_file = cast(
                dict[str, list[dict[str, Any]]],
                getattr(self.indexer, "symbols", {}),
            )
            for file_path in symbols_by_file:
                path = Path(file_path)
                if path.exists() and self._inside_repo(path, repo_path):
                    indexed_paths.append(path.resolve())
            return indexed_paths[:200]

        resolved_paths: list[Path] = []
        for raw_path in paths:
            path = Path(raw_path).expanduser()
            if not path.is_absolute():
                path = repo_path / path
            if path.exists():
                resolved_paths.append(path.resolve())
        return resolved_paths

    def _run_process(
        self,
        command: list[str] | str,
        cwd: Path,
        timeout_seconds: int = 120,
        shell: bool = False,
    ) -> dict[str, Any]:
        try:
            result = subprocess.run(
                command,
                cwd=str(cwd),
                shell=shell,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
            )
            return {
                "command": command if isinstance(command, str) else " ".join(command),
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "command": command if isinstance(command, str) else " ".join(command),
                "returncode": None,
                "stdout": "",
                "stderr": f"Таймаут команды после {timeout_seconds} секунд",
                "timeout": True,
            }
        except Exception as exc:
            return {
                "command": command if isinstance(command, str) else " ".join(command),
                "returncode": None,
                "stdout": "",
                "stderr": str(exc),
                "error": str(exc),
            }

    def _symbol_records(self, target: Optional[str] = None) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        query = target.lower() if target else None
        symbols_by_file = cast(
            dict[str, list[dict[str, Any]]],
            getattr(self.indexer, "symbols", {}),
        )
        for file_path, symbols in symbols_by_file.items():
            for symbol in symbols:
                name = str(symbol.get("name", ""))
                if query and name != target and query not in name.lower():
                    continue
                records.append(
                    {
                        "name": name,
                        "file": symbol.get("file", file_path),
                        "start": symbol.get("start", 0),
                        "end": symbol.get("end", 0),
                    }
                )
        return records

    def impact_analysis(
        self,
        target: str,
        repo: Optional[str] = None,
        max_depth: int = 2,
    ) -> dict[str, Any]:
        """Возвращает область влияния символа по текущему AST/call/import graph."""
        try:
            repo_path = self._resolve_repo(repo)
        except ValueError as exc:
            return {"error": str(exc)}

        max_depth = max(1, min(max_depth, 5))
        all_symbol_records = self._symbol_records()
        internal_symbol_names = {record["name"] for record in all_symbol_records}
        matches = [
            record
            for record in all_symbol_records
            if record["name"] == target or target.lower() in record["name"].lower()
        ]
        target_names = {record["name"] for record in matches} or {target}
        call_graph = cast(
            dict[str, set[str]],
            getattr(getattr(self.indexer, "graphs", None), "call_graph", {}),
        )
        import_graph = cast(
            dict[str, list[str]],
            getattr(getattr(self.indexer, "graphs", None), "import_graph", {}),
        )

        affected_symbols = set(target_names)
        direct_callers: set[str] = set()
        direct_callees: set[str] = set()
        external_callees: set[str] = set()
        edges: list[dict[str, Any]] = []
        queue = deque((name, 0) for name in target_names)
        visited = set(target_names)

        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue

            for caller, callees in call_graph.items():
                callee_set = set(callees)
                if any(_callee_matches(callee, {current}) for callee in callee_set):
                    direct_callers.add(caller)
                    affected_symbols.add(caller)
                    edges.append(
                        {
                            "type": "CALLS",
                            "from": caller,
                            "to": current,
                            "direction": "incoming",
                            "depth": depth + 1,
                        }
                    )
                    if caller not in visited:
                        visited.add(caller)
                        queue.append((caller, depth + 1))

            for callee in call_graph.get(current, set()):
                callee_name = _last_identifier(callee)
                direct_callees.add(callee_name)
                edges.append(
                    {
                        "type": "CALLS",
                        "from": current,
                        "to": callee_name,
                        "direction": "outgoing",
                        "depth": depth + 1,
                        "resolved": callee_name in internal_symbol_names,
                    }
                )
                if callee_name not in internal_symbol_names:
                    external_callees.add(callee_name)
                    continue

                affected_symbols.add(callee_name)
                if callee_name not in visited:
                    visited.add(callee_name)
                    queue.append((callee_name, depth + 1))

        symbol_files: defaultdict[str, set[str]] = defaultdict(set)
        for record in all_symbol_records:
            if record["name"] in affected_symbols:
                symbol_files[record["name"]].add(record["file"])

        import_hits: list[dict[str, str]] = []
        target_lower = target.lower()
        for file_path, imports in import_graph.items():
            for import_text in imports:
                if target_lower in str(import_text).lower():
                    import_hits.append({"file": file_path, "import": import_text})

        affected_files: list[str] = sorted(
            {
                file_path
                for files in symbol_files.values()
                for file_path in files
                if self._inside_repo(Path(file_path), repo_path)
            }
            | {hit["file"] for hit in import_hits}
        )
        tests = self._suggest_tests(repo_path, target_names, affected_files)
        blast_radius = {
            "symbols": len(affected_symbols),
            "files": len(affected_files),
            "direct_callers": len(direct_callers),
            "direct_callees": len(direct_callees),
            "external_callees": len(external_callees),
            "imports": len(import_hits),
        }
        risk = self._rank_risk(blast_radius)

        return {
            "target": target,
            "repo": str(repo_path),
            "matches": matches[:20],
            "direct_callers": sorted(direct_callers),
            "direct_callees": sorted(direct_callees),
            "external_callees": sorted(external_callees),
            "affected_symbols": sorted(affected_symbols),
            "affected_files": affected_files,
            "import_hits": import_hits[:50],
            "blast_radius": blast_radius,
            "risk": risk,
            "suggested_tests": tests,
            "knowledge_graph": {
                "nodes": sorted(affected_symbols),
                "edges": edges[:200],
                "storage": "in_memory",
                "upgrade_path": "Neo4j/Memgraph adapter can persist the same nodes and edges.",
            },
        }

    def _suggest_tests(
        self,
        repo_path: Path,
        target_names: set[str],
        affected_files: list[str],
    ) -> list[str]:
        test_candidates: list[str] = []
        target_tokens = {name.lower() for name in target_names}
        affected_stems = {Path(file_path).stem.lower() for file_path in affected_files}

        symbols_by_file = cast(
            dict[str, list[dict[str, Any]]],
            getattr(self.indexer, "symbols", {}),
        )
        for file_path in symbols_by_file:
            path = Path(file_path)
            if not self._inside_repo(path, repo_path):
                continue
            lowered = path.as_posix().lower()
            if "test" not in lowered:
                continue
            if any(token in lowered for token in target_tokens | affected_stems):
                test_candidates.append(str(path))

        if test_candidates:
            return sorted(set(test_candidates))[:20]

        tests_dir = repo_path / "tests"
        if tests_dir.exists():
            return [str(path) for path in sorted(tests_dir.rglob("test_*.py"))[:20]]
        return []

    def _rank_risk(self, blast_radius: dict[str, int]) -> dict[str, Any]:
        score = (
            blast_radius["symbols"]
            + blast_radius["files"] * 2
            + blast_radius["direct_callers"] * 2
            + blast_radius["imports"]
        )
        if score >= 30:
            level = "high"
        elif score >= 10:
            level = "medium"
        else:
            level = "low"
        return {"level": level, "score": score}

    def git_intelligence(
        self,
        path: Optional[str] = None,
        symbol: Optional[str] = None,
        repo: Optional[str] = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        """Возвращает git history/blame для файла или символа."""
        try:
            repo_path = self._resolve_repo(repo)
        except ValueError as exc:
            return {"error": str(exc)}

        if not shutil.which("git"):
            return {"error": "git не найден в PATH"}

        target_path = self._resolve_git_target(path, symbol, repo_path)
        if target_path and not self._inside_repo(target_path, repo_path):
            return {"error": f"Путь вне репозитория: {target_path}"}

        rel_args = []
        if target_path:
            rel_args = ["--", self._relative(target_path, repo_path)]

        log_command = [
            "git",
            "log",
            f"-{max(1, min(limit, 50))}",
            "--date=iso-strict",
            "--pretty=format:%H%x1f%an%x1f%ad%x1f%s",
            *rel_args,
        ]
        log_result = self._run_process(log_command, repo_path, timeout_seconds=30)
        commits = self._parse_git_log(log_result.get("stdout", ""))

        blame = []
        if target_path and target_path.exists():
            blame = self._collect_blame(repo_path, target_path, symbol, limit)

        return {
            "repo": str(repo_path),
            "path": str(target_path) if target_path else None,
            "symbol": symbol,
            "commits": commits,
            "blame": blame,
            "history_hint": self._history_hint(commits, blame),
            "errors": {
                "log": log_result.get("stderr") if log_result.get("returncode") else None,
            },
        }

    def _resolve_git_target(
        self,
        path: Optional[str],
        symbol: Optional[str],
        repo_path: Path,
    ) -> Optional[Path]:
        if path:
            target_path = Path(path).expanduser()
            if not target_path.is_absolute():
                target_path = repo_path / target_path
            return target_path.resolve()

        if symbol:
            matches = self._symbol_records(symbol)
            if matches:
                return Path(matches[0]["file"]).resolve()
        return None

    def _parse_git_log(self, stdout: str) -> list[dict[str, str]]:
        commits: list[dict[str, str]] = []
        for line in stdout.splitlines():
            parts = line.split("\x1f")
            if len(parts) != 4:
                continue
            commit_hash, author, date, message = parts
            commits.append(
                {
                    "hash": commit_hash,
                    "short_hash": commit_hash[:12],
                    "author": author,
                    "date": date,
                    "message": message,
                }
            )
        return commits

    def _collect_blame(
        self,
        repo_path: Path,
        target_path: Path,
        symbol: Optional[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        line_args = []
        if symbol:
            for record in self._symbol_records(symbol):
                if Path(record["file"]).resolve() == target_path:
                    start = int(record.get("start", 0)) + 1
                    end = max(start, int(record.get("end", start)) + 1)
                    line_args = ["-L", f"{start},{end}"]
                    break

        command = [
            "git",
            "blame",
            *line_args,
            "--line-porcelain",
            "--",
            self._relative(target_path, repo_path),
        ]
        result = self._run_process(command, repo_path, timeout_seconds=30)
        if result.get("returncode") not in (0, None):
            return []

        entries: list[dict[str, Any]] = []
        current: dict[str, Any] = {}
        seen_hashes: set[str] = set()
        for line in result.get("stdout", "").splitlines():
            if re.match(r"^[0-9a-f]{40} ", line):
                commit_hash = line.split(" ", 1)[0]
                current = {"hash": commit_hash, "short_hash": commit_hash[:12]}
            elif line.startswith("author "):
                current["author"] = line.removeprefix("author ")
            elif line.startswith("author-time "):
                timestamp = int(line.removeprefix("author-time "))
                current["date"] = datetime.fromtimestamp(
                    timestamp,
                    tz=timezone.utc,
                ).isoformat()
            elif line.startswith("summary "):
                current["summary"] = line.removeprefix("summary ")
            elif line.startswith("\t") and current.get("hash") not in seen_hashes:
                seen_hashes.add(current["hash"])
                current["sample_line"] = line[1:160]
                entries.append(current.copy())
                if len(entries) >= limit:
                    break
        return entries

    def _history_hint(
        self,
        commits: list[dict[str, str]],
        blame: list[dict[str, Any]],
    ) -> str:
        if blame:
            first = blame[0]
            return (
                "Ближайший контекст изменения: "
                f"{first.get('short_hash')} {first.get('summary', '')}"
            )
        if commits:
            first = commits[0]
            return f"Последний релевантный commit: {first['short_hash']} {first['message']}"
        return "История не найдена или файл пока не отслеживается git."

    def remember_project_fact(
        self,
        category: str,
        fact: str,
        confidence: float = 1.0,
        source: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> dict[str, Any]:
        """Сохраняет структурированный факт в `.agents/booster/memory.json`."""
        try:
            repo_path = self._resolve_repo(repo)
        except ValueError as exc:
            return {"error": str(exc)}

        memory = self._load_memory(repo_path)
        facts = cast(list[dict[str, Any]], memory.setdefault("_booster_project_facts", []))
        fact_id = hashlib.sha1(f"{category}:{fact}".encode("utf-8")).hexdigest()[:12]
        normalized_confidence = max(0.0, min(float(confidence), 1.0))
        payload: dict[str, Any] = {
            "id": fact_id,
            "category": category,
            "fact": fact,
            "confidence": normalized_confidence,
            "source": source,
            "updated_at_utc": _utc_now(),
        }

        for index, existing in enumerate(facts):
            if existing.get("id") == fact_id:
                facts[index] = payload
                break
        else:
            facts.append(payload)

        self._save_memory(repo_path, memory)
        return {"repo": str(repo_path), "fact": payload, "count": len(facts)}

    def project_memory_recall(
        self,
        query: Optional[str] = None,
        categories: Optional[list[str]] = None,
        repo: Optional[str] = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Возвращает релевантные долгосрочные факты и legacy memory keys."""
        try:
            repo_path = self._resolve_repo(repo)
        except ValueError as exc:
            return {"error": str(exc)}

        memory = self._load_memory(repo_path)
        facts = cast(list[dict[str, Any]], list(memory.get("_booster_project_facts", [])))
        requested_categories = set(categories or [])
        query_tokens = set(re.findall(r"[A-Za-zА-Яа-я0-9_]+", query or ""))
        query_tokens = {token.lower() for token in query_tokens if len(token) > 2}

        scored_facts: list[tuple[float, dict[str, Any]]] = []
        for fact in facts:
            if requested_categories and fact.get("category") not in requested_categories:
                continue
            haystack = f"{fact.get('category', '')} {fact.get('fact', '')}".lower()
            score = float(fact.get("confidence", 0.5))
            if query_tokens:
                score += sum(1 for token in query_tokens if token in haystack)
            if not query_tokens or score > float(fact.get("confidence", 0.5)):
                scored_facts.append((score, fact))

        scored_facts.sort(key=lambda item: item[0], reverse=True)
        selected_facts: list[dict[str, Any]] = [
            fact for _, fact in scored_facts[: max(1, min(limit, 100))]
        ]
        legacy_keys = [key for key in memory.keys() if not key.startswith("_booster_")]

        return {
            "repo": str(repo_path),
            "query": query,
            "facts": selected_facts,
            "legacy_keys": legacy_keys,
            "context": "\n".join(
                f"- [{fact.get('category')}] {fact.get('fact')}" for fact in selected_facts
            ),
        }

    def collect_diagnostics(
        self,
        paths: Optional[list[str]] = None,
        repo: Optional[str] = None,
        include_security: bool = True,
        run_external: bool = True,
        timeout_seconds: int = 120,
    ) -> dict[str, Any]:
        """Собирает diagnostics из компиляторов, typecheckers и security scanners."""
        try:
            repo_path = self._resolve_repo(repo)
        except ValueError as exc:
            return {"error": str(exc)}

        target_paths = self._resolve_paths(paths, repo_path)
        source_paths = [path for path in target_paths if path.suffix in SOURCE_EXTENSIONS]
        findings: list[dict[str, Any]] = []
        commands: list[dict[str, Any]] = []
        skipped_tools: list[dict[str, str]] = []

        python_paths = [path for path in source_paths if path.suffix in PYTHON_EXTENSIONS]
        for path in python_paths:
            command, finding = self._compile_python_syntax(path)
            commands.append(command)
            if finding:
                findings.append(finding)

        if run_external:
            findings.extend(
                self._collect_ruff(
                    repo_path,
                    python_paths,
                    commands,
                    skipped_tools,
                    timeout_seconds,
                )
            )
            findings.extend(
                self._collect_pyright(
                    repo_path,
                    python_paths,
                    commands,
                    skipped_tools,
                    timeout_seconds,
                )
            )
            findings.extend(
                self._collect_typescript(
                    repo_path,
                    source_paths,
                    commands,
                    skipped_tools,
                    timeout_seconds,
                )
            )
            findings.extend(
                self._collect_rust(
                    repo_path,
                    source_paths,
                    commands,
                    skipped_tools,
                    timeout_seconds,
                )
            )

            if include_security:
                findings.extend(
                    self._collect_security(
                        repo_path,
                        source_paths,
                        commands,
                        skipped_tools,
                        timeout_seconds,
                    )
                )

        summary = self._diagnostics_summary(findings)
        return {
            "repo": str(repo_path),
            "paths_checked": [str(path) for path in source_paths],
            "summary": summary,
            "findings": findings,
            "commands": commands,
            "skipped_tools": skipped_tools,
        }

    def security_audit(
        self,
        paths: Optional[list[str]] = None,
        repo: Optional[str] = None,
        run_external: bool = True,
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        """Запускает bounded security-only audit без блокировки обычного workflow."""
        try:
            repo_path = self._resolve_repo(repo)
        except ValueError as exc:
            return {"error": str(exc)}

        target_paths = self._resolve_paths(paths, repo_path)
        if not target_paths:
            try:
                target_paths = [
                    path.resolve() for path in RepositoryScanner(repo_path).scan().files
                ]
            except Exception as exc:
                return {
                    "repo": str(repo_path),
                    "status": "error",
                    "error": f"Не удалось определить файлы для security audit: {exc}",
                }
        source_paths = [path for path in target_paths if path.suffix.lower() in SOURCE_EXTENSIONS]
        bounded_timeout = max(1, min(int(timeout_seconds), 300))
        commands: list[dict[str, Any]] = []
        skipped_tools: list[dict[str, str]] = []
        if run_external and source_paths:
            findings = self._collect_security(
                repo_path,
                source_paths,
                commands,
                skipped_tools,
                bounded_timeout,
            )
        else:
            findings = []
            reason = "external_scanners_disabled" if not run_external else "no_source_files"
            skipped_tools.append({"tool": "security_audit", "reason": reason})

        summary = self._diagnostics_summary(findings)
        if summary["status"] == "failed":
            pass
        elif not source_paths:
            summary["status"] = "incomplete"
        elif not run_external:
            summary["status"] = "not_run"
        elif skipped_tools:
            summary["status"] = "incomplete"
        return {
            "repo": str(repo_path),
            "paths_checked": [str(path) for path in source_paths],
            "status": summary["status"],
            "summary": summary,
            "findings": findings,
            "commands": commands,
            "skipped_tools": skipped_tools,
            "coverage": {
                "mode": "external" if run_external else "disabled",
                "tools": sorted({str(item.get("tool")) for item in commands}),
                "advisory": True,
            },
        }

    def _summarize_command(self, tool: str, result: dict[str, Any]) -> dict[str, Any]:
        returncode = result.get("returncode")
        timed_out = bool(result.get("timeout"))
        return {
            "tool": tool,
            "command": result.get("command"),
            "returncode": returncode,
            "status": self._command_status(result),
            "timeout": timed_out,
            "stdout_tail": result.get("stdout", "")[-2000:],
            "stderr_tail": result.get("stderr", "")[-2000:],
        }

    def _command_status(self, result: dict[str, Any]) -> str:
        if result.get("timeout"):
            return "timeout"
        if result.get("error"):
            return "error"
        if result.get("returncode") == 0:
            return "passed"
        return "failed"

    def _command_failed(self, result: dict[str, Any]) -> bool:
        return self._command_status(result) != "passed"

    def _command_failure_finding(
        self,
        tool: str,
        result: dict[str, Any],
        file: Optional[Path] = None,
    ) -> dict[str, Any]:
        stderr = result.get("stderr", "").strip()
        stdout = result.get("stdout", "").strip()
        message = stderr or stdout or f"{tool} завершился без диагностического вывода"
        return {
            "source": tool,
            "severity": "error",
            "file": str(file) if file else None,
            "line": None,
            "message": message[-2000:],
            "rule": "tool_execution_failed",
            "status": self._command_status(result),
            "returncode": result.get("returncode"),
        }

    def _tool_command(self, binary: str, module: Optional[str] = None) -> Optional[list[str]]:
        executable = shutil.which(binary)
        if executable:
            return [executable]
        if module and importlib.util.find_spec(module):
            return [sys.executable, "-m", module]
        return None

    def _compile_python_syntax(self, path: Path) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
        command: dict[str, Any] = {
            "tool": "py_compile",
            "command": f"internal compile({path})",
            "returncode": 0,
            "status": "passed",
            "timeout": False,
            "stdout_tail": "",
            "stderr_tail": "",
        }
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
            compile(source, str(path), "exec")
            return command, None
        except SyntaxError as exc:
            message = exc.msg or "Python syntax error"
            command.update(
                {
                    "returncode": 1,
                    "status": "failed",
                    "stderr_tail": message,
                }
            )
            return command, {
                "source": "py_compile",
                "severity": "error",
                "file": str(path),
                "line": exc.lineno,
                "column": exc.offset,
                "message": message,
                "rule": "python_syntax_error",
            }
        except Exception as exc:
            command.update(
                {
                    "returncode": 1,
                    "status": "error",
                    "stderr_tail": str(exc),
                }
            )
            return command, {
                "source": "py_compile",
                "severity": "error",
                "file": str(path),
                "line": None,
                "message": str(exc),
                "rule": "tool_execution_failed",
                "status": "error",
            }

    def _parse_py_compile_error(self, path: Path, stderr: str) -> dict[str, Any]:
        line_match = re.search(r'File "[^"]+", line (\d+)', stderr)
        line = int(line_match.group(1)) if line_match else None
        message = stderr.strip().splitlines()[-1] if stderr.strip() else "Python syntax error"
        return {
            "source": "py_compile",
            "severity": "error",
            "file": str(path),
            "line": line,
            "message": message,
        }

    def _collect_pyright(
        self,
        repo_path: Path,
        python_paths: list[Path],
        commands: list[dict[str, Any]],
        skipped_tools: list[dict[str, str]],
        timeout_seconds: int,
    ) -> list[dict[str, Any]]:
        if not python_paths:
            return []
        pyright = shutil.which("pyright")
        if not pyright:
            skipped_tools.append({"tool": "pyright", "reason": "binary_not_found"})
            return []

        command = [pyright, "--outputjson", *[str(path) for path in python_paths]]
        result = self._run_process(command, repo_path, timeout_seconds=timeout_seconds)
        commands.append(self._summarize_command("pyright", result))
        try:
            payload = cast(dict[str, Any], json.loads(result.get("stdout", "") or "{}"))
        except json.JSONDecodeError:
            return [self._command_failure_finding("pyright", result)]

        findings: list[dict[str, Any]] = []
        for diagnostic in payload.get("generalDiagnostics", []):
            range_start = diagnostic.get("range", {}).get("start", {})
            findings.append(
                {
                    "source": "pyright",
                    "severity": diagnostic.get("severity", "error"),
                    "file": diagnostic.get("file"),
                    "line": range_start.get("line", 0) + 1,
                    "column": range_start.get("character", 0) + 1,
                    "message": diagnostic.get("message", ""),
                    "rule": diagnostic.get("rule"),
                }
            )
        if not findings and self._command_failed(result):
            findings.append(self._command_failure_finding("pyright", result))
        return findings

    def _collect_ruff(
        self,
        repo_path: Path,
        python_paths: list[Path],
        commands: list[dict[str, Any]],
        skipped_tools: list[dict[str, str]],
        timeout_seconds: int,
    ) -> list[dict[str, Any]]:
        if not python_paths:
            return []
        command_prefix = self._tool_command("ruff", "ruff")
        if not command_prefix:
            skipped_tools.append({"tool": "ruff", "reason": "binary_or_module_not_found"})
            return []

        command = [
            *command_prefix,
            "check",
            "--output-format",
            "json",
            *[str(path) for path in python_paths],
        ]
        result = self._run_process(command, repo_path, timeout_seconds=timeout_seconds)
        commands.append(self._summarize_command("ruff", result))
        findings = self._parse_ruff(result.get("stdout", ""))
        if not findings and self._command_failed(result):
            findings.append(self._command_failure_finding("ruff", result))
        return findings

    def _parse_ruff(self, stdout: str) -> list[dict[str, Any]]:
        try:
            payload = cast(list[dict[str, Any]], json.loads(stdout or "[]"))
        except json.JSONDecodeError:
            return []

        findings: list[dict[str, Any]] = []
        for item in payload:
            code = str(item.get("code") or "")
            location = cast(dict[str, Any], item.get("location", {}))
            severity = "error" if code.startswith(("F", "E9")) else "warning"
            findings.append(
                {
                    "source": "ruff",
                    "severity": severity,
                    "file": item.get("filename"),
                    "line": location.get("row"),
                    "column": location.get("column"),
                    "message": item.get("message"),
                    "rule": code,
                }
            )
        return findings

    def _collect_typescript(
        self,
        repo_path: Path,
        source_paths: list[Path],
        commands: list[dict[str, Any]],
        skipped_tools: list[dict[str, str]],
        timeout_seconds: int,
    ) -> list[dict[str, Any]]:
        if not any(path.suffix in TYPESCRIPT_EXTENSIONS for path in source_paths):
            return []
        tsc = shutil.which("tsc")
        if not tsc:
            skipped_tools.append({"tool": "tsc", "reason": "binary_not_found"})
            return []
        if not (repo_path / "tsconfig.json").exists():
            skipped_tools.append({"tool": "tsc", "reason": "tsconfig_not_found"})
            return []

        result = self._run_process(
            [tsc, "--noEmit", "--pretty", "false"],
            repo_path,
            timeout_seconds=timeout_seconds,
        )
        commands.append(self._summarize_command("tsc", result))
        output = "\n".join([result.get("stdout", ""), result.get("stderr", "")])
        findings: list[dict[str, Any]] = []
        pattern = re.compile(r"(.+)\((\d+),(\d+)\): (error|warning) (TS\d+): (.+)")
        for line in output.splitlines():
            match = pattern.match(line.strip())
            if not match:
                continue
            file_path, line_no, column, severity, code, message = match.groups()
            findings.append(
                {
                    "source": "tsc",
                    "severity": severity,
                    "file": str((repo_path / file_path).resolve()),
                    "line": int(line_no),
                    "column": int(column),
                    "message": message,
                    "rule": code,
                }
            )
        if not findings and self._command_failed(result):
            findings.append(self._command_failure_finding("tsc", result))
        return findings

    def _collect_rust(
        self,
        repo_path: Path,
        source_paths: list[Path],
        commands: list[dict[str, Any]],
        skipped_tools: list[dict[str, str]],
        timeout_seconds: int,
    ) -> list[dict[str, Any]]:
        if not any(path.suffix in RUST_EXTENSIONS for path in source_paths):
            return []
        cargo = shutil.which("cargo")
        if not cargo:
            skipped_tools.append({"tool": "cargo check", "reason": "binary_not_found"})
            return []
        if not (repo_path / "Cargo.toml").exists():
            skipped_tools.append({"tool": "cargo check", "reason": "Cargo.toml_not_found"})
            return []

        result = self._run_process(
            [cargo, "check", "--message-format=json"],
            repo_path,
            timeout_seconds=timeout_seconds,
        )
        commands.append(self._summarize_command("cargo check", result))
        findings: list[dict[str, Any]] = []
        for line in result.get("stdout", "").splitlines():
            try:
                payload = cast(dict[str, Any], json.loads(line))
            except json.JSONDecodeError:
                continue
            if payload.get("reason") != "compiler-message":
                continue
            message = cast(dict[str, Any], payload.get("message", {}))
            spans = cast(list[dict[str, Any]], message.get("spans") or [{}])
            primary = next((span for span in spans if span.get("is_primary")), spans[0])
            file_name = str(primary.get("file_name", ""))
            findings.append(
                {
                    "source": "cargo check",
                    "severity": message.get("level", "error"),
                    "file": str((repo_path / file_name).resolve()),
                    "line": primary.get("line_start"),
                    "column": primary.get("column_start"),
                    "message": message.get("message", ""),
                    "rule": message.get("code", {}).get("code"),
                }
            )
        if not findings and self._command_failed(result):
            findings.append(self._command_failure_finding("cargo check", result))
        return findings

    def _collect_security(
        self,
        repo_path: Path,
        source_paths: list[Path],
        commands: list[dict[str, Any]],
        skipped_tools: list[dict[str, str]],
        timeout_seconds: int,
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        python_paths = [path for path in source_paths if path.suffix in PYTHON_EXTENSIONS]
        bandit = shutil.which("bandit")
        if python_paths and bandit:
            command = [bandit, "-q", "-f", "json", *[str(path) for path in python_paths]]
            result = self._run_process(command, repo_path, timeout_seconds=timeout_seconds)
            commands.append(self._summarize_command("bandit", result))
            parsed = self._parse_bandit(result.get("stdout", ""))
            findings.extend(parsed)
            if not parsed and self._command_failed(result):
                findings.append(self._command_failure_finding("bandit", result))
        elif python_paths:
            skipped_tools.append({"tool": "bandit", "reason": "binary_not_found"})

        semgrep = shutil.which("semgrep")
        if semgrep:
            command = [semgrep, "--config=auto", "--json", *[str(path) for path in source_paths]]
            result = self._run_process(command, repo_path, timeout_seconds=timeout_seconds)
            commands.append(self._summarize_command("semgrep", result))
            parsed = self._parse_semgrep(result.get("stdout", ""))
            findings.extend(parsed)
            if not parsed and self._command_failed(result):
                findings.append(self._command_failure_finding("semgrep", result))
        elif source_paths:
            skipped_tools.append({"tool": "semgrep", "reason": "binary_not_found"})
        return findings

    def _parse_bandit(self, stdout: str) -> list[dict[str, Any]]:
        try:
            payload = cast(dict[str, Any], json.loads(stdout or "{}"))
        except json.JSONDecodeError:
            return []
        findings: list[dict[str, Any]] = []
        for item in payload.get("results", []):
            findings.append(
                {
                    "source": "bandit",
                    "severity": str(item.get("issue_severity", "warning")).lower(),
                    "file": item.get("filename"),
                    "line": item.get("line_number"),
                    "message": item.get("issue_text"),
                    "rule": item.get("test_id"),
                    "confidence": item.get("issue_confidence"),
                }
            )
        return findings

    def _parse_semgrep(self, stdout: str) -> list[dict[str, Any]]:
        try:
            payload = cast(dict[str, Any], json.loads(stdout or "{}"))
        except json.JSONDecodeError:
            return []
        findings: list[dict[str, Any]] = []
        for item in payload.get("results", []):
            extra = item.get("extra", {})
            findings.append(
                {
                    "source": "semgrep",
                    "severity": extra.get("severity", "warning").lower(),
                    "file": item.get("path"),
                    "line": item.get("start", {}).get("line"),
                    "column": item.get("start", {}).get("col"),
                    "message": extra.get("message"),
                    "rule": item.get("check_id"),
                }
            )
        return findings

    def _diagnostics_summary(self, findings: list[dict[str, Any]]) -> dict[str, Any]:
        counts: defaultdict[str, int] = defaultdict(int)
        for finding in findings:
            counts[str(finding.get("severity", "unknown")).lower()] += 1

        failing_levels = {"error", "critical", "high", "fatal"}
        status = "failed" if any(counts[level] for level in failing_levels) else "passed"
        return {"status": status, "total": len(findings), "by_severity": dict(counts)}

    def preflight_analysis(
        self,
        task: str,
        target: Optional[str] = None,
        paths: Optional[list[str]] = None,
        repo: Optional[str] = None,
        run_diagnostics: bool = True,
    ) -> dict[str, Any]:
        """Собирает память, impact и diagnostics перед изменением кода."""
        try:
            repo_path = self._resolve_repo(repo)
        except ValueError as exc:
            return {"error": str(exc)}

        resolved_target = target or self._infer_target_from_task(task)
        memory = self.project_memory_recall(query=task, repo=str(repo_path))
        impact = (
            self.impact_analysis(resolved_target, repo=str(repo_path), max_depth=2)
            if resolved_target
            else {"warning": "Целевой символ не определен"}
        )
        diagnostics = (
            self.collect_diagnostics(
                paths=paths,
                repo=str(repo_path),
                include_security=False,
                run_external=False,
                timeout_seconds=30,
            )
            if run_diagnostics
            else {"skipped": True}
        )

        return {
            "task": task,
            "repo": str(repo_path),
            "target": resolved_target,
            "project_memory": memory,
            "impact": impact,
            "diagnostics": diagnostics,
            "recommended_order": [
                "прочитать релевантную память проекта",
                "оценить blast radius",
                "исправить существующие diagnostics только в зоне задачи",
                "внести минимальный patch",
                "запустить validation checks",
            ],
        }

    def _infer_target_from_task(self, task: str) -> Optional[str]:
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", task)
        symbols = self._symbol_records()
        names = {record["name"] for record in symbols}
        for token in tokens:
            if token in names:
                return token
        lowered_names = {name.lower(): name for name in names}
        for token in tokens:
            if token.lower() in lowered_names:
                return lowered_names[token.lower()]
        return None

    def validation_loop_plan(
        self,
        task: str,
        changed_paths: Optional[list[str]] = None,
        repo: Optional[str] = None,
        max_iterations: int = 5,
    ) -> dict[str, Any]:
        """Строит инженерный цикл проверки для агента без изменения файлов."""
        try:
            repo_path = self._resolve_repo(repo)
        except ValueError as exc:
            return {"error": str(exc)}

        commands = self._default_validation_commands(repo_path)
        return {
            "task": task,
            "repo": str(repo_path),
            "changed_paths": changed_paths or [],
            "max_iterations": max(1, min(max_iterations, 10)),
            "loop": [
                "Plan",
                "Implement",
                "collect_diagnostics",
                "run_validation_checks",
                "Analyze failures",
                "Repair same slice",
                "Repeat until passed or max_iterations",
            ],
            "recommended_commands": commands,
            "stop_conditions": [
                "validation passed",
                "hypothesis falsified by diagnostics/tests",
                "failure leaves touched slice and needs user decision",
            ],
        }

    def _default_validation_commands(self, repo_path: Path) -> list[str]:
        commands: list[str] = []
        if (repo_path / "tests").exists() and (repo_path / "pyproject.toml").exists():
            commands.append(f'"{sys.executable}" -m pytest tests -q')
        if (repo_path / "package.json").exists():
            commands.append("npm test")
        if (repo_path / "Cargo.toml").exists():
            commands.append("cargo test")
        return commands

    def run_validation_checks(
        self,
        commands: Optional[list[str]] = None,
        paths: Optional[list[str]] = None,
        repo: Optional[str] = None,
        timeout_seconds: int = 120,
    ) -> dict[str, Any]:
        """Запускает diagnostics и указанные команды проверки одним проходом."""
        try:
            repo_path = self._resolve_repo(repo)
        except ValueError as exc:
            return {"error": str(exc)}

        diagnostics = self.collect_diagnostics(
            paths=paths,
            repo=str(repo_path),
            include_security=True,
            run_external=True,
            timeout_seconds=timeout_seconds,
        )
        selected_commands = (
            commands if commands is not None else self._default_validation_commands(repo_path)
        )
        command_results: list[dict[str, Any]] = []
        for command in selected_commands:
            result = self._run_process(
                command,
                repo_path,
                timeout_seconds=timeout_seconds,
                shell=True,
            )
            command_results.append(
                {
                    "command": command,
                    "returncode": result.get("returncode"),
                    "stdout_tail": result.get("stdout", "")[-5000:],
                    "stderr_tail": result.get("stderr", "")[-5000:],
                    "passed": result.get("returncode") == 0,
                }
            )

        failed_commands: list[dict[str, Any]] = [
            item for item in command_results if not item["passed"]
        ]
        status = (
            "failed"
            if failed_commands or diagnostics["summary"]["status"] == "failed"
            else "passed"
        )
        return {
            "repo": str(repo_path),
            "status": status,
            "diagnostics": diagnostics,
            "commands": command_results,
            "next_step": self._next_validation_step(status, diagnostics, failed_commands),
        }

    def _next_validation_step(
        self,
        status: str,
        diagnostics: dict[str, Any],
        failed_commands: list[dict[str, Any]],
    ) -> str:
        if status == "passed":
            return "Можно переходить к review/diff и финальному отчету."
        if diagnostics["summary"]["status"] == "failed":
            return "Сначала исправь diagnostics в затронутых файлах и повтори проверку."
        if failed_commands:
            return "Разбери первый failing command, сузь причину и повтори тот же check."
        return "Нужна ручная диагностика: статус failed без нормализованной причины."


def setup_cognitive_runtime_tools(mcp: Any, indexer: Any, repos: list[str]):
    """Регистрирует Cognitive Runtime инструменты в MCP сервере."""
    runtime = CognitiveRuntime(indexer, repos)

    @mcp.tool()
    def impact_analysis(target: str, repo: Optional[str] = None, max_depth: int = 2):
        """Оценивает область влияния символа через AST/call/import graph."""
        return runtime.impact_analysis(target, repo, max_depth)

    @mcp.tool()
    def git_intelligence(
        path: Optional[str] = None,
        symbol: Optional[str] = None,
        repo: Optional[str] = None,
        limit: int = 8,
    ):
        """Показывает git history/blame для файла или символа."""
        return runtime.git_intelligence(path, symbol, repo, limit)

    @mcp.tool()
    def remember_project_fact(
        category: str,
        fact: str,
        confidence: float = 1.0,
        source: Optional[str] = None,
        repo: Optional[str] = None,
    ):
        """Сохраняет структурированный факт долгосрочной памяти проекта."""
        return runtime.remember_project_fact(category, fact, confidence, source, repo)

    @mcp.tool()
    def project_memory_recall(
        query: Optional[str] = None,
        categories: Optional[list[str]] = None,
        repo: Optional[str] = None,
        limit: int = 20,
    ):
        """Возвращает релевантные факты project memory для задачи."""
        return runtime.project_memory_recall(query, categories, repo, limit)

    @mcp.tool()
    def collect_diagnostics(
        paths: Optional[list[str]] = None,
        repo: Optional[str] = None,
        include_security: bool = True,
        run_external: bool = True,
        timeout_seconds: int = 120,
    ):
        """Собирает Python/Pyright/TS/Rust/security diagnostics."""
        return runtime.collect_diagnostics(
            paths,
            repo,
            include_security,
            run_external,
            timeout_seconds,
        )

    @mcp.tool()
    def security_audit(
        paths: Optional[list[str]] = None,
        repo: Optional[str] = None,
        run_external: bool = True,
        timeout_seconds: int = 60,
    ):
        """Запускает advisory security audit через доступные Bandit/Semgrep scanners."""
        return runtime.security_audit(paths, repo, run_external, timeout_seconds)

    @mcp.tool()
    def preflight_analysis(
        task: str,
        target: Optional[str] = None,
        paths: Optional[list[str]] = None,
        repo: Optional[str] = None,
        run_diagnostics: bool = True,
    ):
        """Собирает память, impact и diagnostics перед изменением кода."""
        return runtime.preflight_analysis(task, target, paths, repo, run_diagnostics)

    @mcp.tool()
    def validation_loop_plan(
        task: str,
        changed_paths: Optional[list[str]] = None,
        repo: Optional[str] = None,
        max_iterations: int = 5,
    ):
        """Формирует цикл Plan -> Implement -> Validate -> Repair."""
        return runtime.validation_loop_plan(task, changed_paths, repo, max_iterations)

    @mcp.tool()
    def run_validation_checks(
        commands: Optional[list[str]] = None,
        paths: Optional[list[str]] = None,
        repo: Optional[str] = None,
        timeout_seconds: int = 120,
    ):
        """Запускает diagnostics и команды проверки для текущего изменения."""
        return runtime.run_validation_checks(commands, paths, repo, timeout_seconds)

    return runtime
