"""Prepare and validate a portable read-only Observatory demo bundle."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess  # nosec B404
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repomap import RepoMap
from repository_lifecycle import RepositorySnapshotStore
from repository_scanner import RepositoryScanner
from visualizer import CodeCityVisualizer

DEMO_ARTIFACTS = (
    "repo_map_architecture.md",
    "repo_map_symbols.md",
    "index_health.json",
    "repo_map.md",
    "scan_config.json",
    "scan_report.json",
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _portable_city(city: dict[str, Any], root: Path) -> dict[str, Any]:
    def portable_value(value: Any, key: str | None = None) -> Any:
        if isinstance(value, dict):
            return {
                str(item_key): portable_value(item_value, str(item_key))
                for item_key, item_value in value.items()
            }
        if isinstance(value, list):
            return [portable_value(item, key) for item in value]
        if key == "file" and isinstance(value, str):
            file_path = Path(value).expanduser()
            if not file_path.is_absolute():
                file_path = root / file_path
            try:
                return file_path.resolve().relative_to(root).as_posix()
            except ValueError:
                return None
        return value

    result = portable_value(city)
    if not isinstance(result, dict):
        return {"repo": "", "buildings": [], "connections": [], "districts": {}, "metrics": {}}
    result["repo"] = ""
    return result


def _safe_snapshot(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metadata.items()
        if key not in {"repository", "snapshot_dir", "artifacts"}
    }


def _portable_diagnostics(diagnostics: Any, root: Path) -> Any:
    if not isinstance(diagnostics, dict):
        return diagnostics
    result = dict(diagnostics)
    checked = result.get("paths_checked")
    if isinstance(checked, list):
        result["paths_checked"] = [
            Path(path).resolve().relative_to(root).as_posix()
            for path in checked
            if isinstance(path, str) and Path(path).resolve().is_relative_to(root)
        ]
    findings = result.get("findings")
    if isinstance(findings, list):
        portable_findings = []
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            item = dict(finding)
            raw_file = item.get("file")
            if isinstance(raw_file, str):
                file_path = Path(raw_file).resolve()
                if not file_path.is_relative_to(root):
                    continue
                item["file"] = file_path.relative_to(root).as_posix()
            portable_findings.append(item)
        result["findings"] = portable_findings
    result.pop("repo", None)
    result.pop("commands", None)
    result.pop("skipped_tools", None)
    return result


def _portable_history(history: Any, root: Path) -> dict[str, Any]:
    if not isinstance(history, dict):
        return {
            "path": None,
            "symbol": None,
            "commits": [],
            "blame": [],
            "history_hint": "Git history is unavailable in the prepared demo.",
        }
    result = {
        "path": None,
        "symbol": history.get("symbol") if isinstance(history.get("symbol"), str) else None,
        "commits": history.get("commits", []) if isinstance(history.get("commits"), list) else [],
        "blame": history.get("blame", []) if isinstance(history.get("blame"), list) else [],
        "history_hint": (
            history.get("history_hint")
            if isinstance(history.get("history_hint"), str)
            else "Git history is unavailable in the prepared demo."
        ),
    }
    raw_path = history.get("path")
    if isinstance(raw_path, str):
        file_path = Path(raw_path).expanduser()
        if not file_path.is_absolute():
            file_path = root / file_path
        file_path = file_path.resolve()
        if file_path.is_relative_to(root):
            result["path"] = file_path.relative_to(root).as_posix()
    return result


def _precompute_history(server: Any, root: Path, paths: list[str]) -> dict[str, Any]:
    records: dict[str, Any] = {}
    for path in paths:
        try:
            value = server.cognitive_runtime.git_intelligence(path, None, str(root), 8)
        except Exception:
            value = None
        records[path] = _portable_history(value, root)
    return {"version": 1, "paths": records}


def _git_text(root: Path, *arguments: str) -> str | None:
    git_executable = shutil.which("git")
    if git_executable is None:
        return None
    try:
        result = subprocess.run(  # nosec B603
            [git_executable, "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _git_blob(root: Path, revision: str, path: str) -> bytes | None:
    git_executable = shutil.which("git")
    if git_executable is None:
        return None
    try:
        result = subprocess.run(  # nosec B603
            [git_executable, "-C", str(root), "cat-file", "blob", f"{revision}:{path}"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _portable_report(report: dict[str, Any]) -> dict[str, Any]:
    result = dict(report)
    result["repository"] = None
    return result


def _write_prepared_snapshot(
    directory: Path,
    snapshot_id: str,
    report: dict[str, Any],
    *,
    commit: str,
    branch: str | None,
    dirty: bool,
) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    report_path = directory / "scan_report.json"
    _write_json(report_path, report)
    report_bytes = report_path.read_bytes()
    report_hash = hashlib.sha256(report_bytes).hexdigest()
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    return {
        "version": 1,
        "snapshot_id": snapshot_id,
        "repository": None,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "commit": commit,
        "commit_short": commit[:12],
        "branch": branch,
        "dirty": dirty,
        "artifact_digest": report_hash,
        "snapshot_dir": str(directory),
        "artifacts": {
            "scan_report.json": {
                "path": str(report_path),
                "size_bytes": len(report_bytes),
                "sha256": report_hash,
            }
        },
        "indexed_files": summary.get("source_files_selected"),
        "reason": "prepared_demo",
        "previous_snapshots_preserved": True,
    }


def _prepare_snapshot_pair(
    root: Path, current_report: dict[str, Any], output: Path
) -> dict[str, str] | None:
    head = _git_text(root, "rev-parse", "HEAD")
    parent = _git_text(root, "rev-parse", "HEAD^")
    raw_manifest = current_report.get("file_manifest")
    if not head or not parent or not isinstance(raw_manifest, dict):
        return None

    baseline_manifest: dict[str, dict[str, Any]] = {}
    for raw_path in raw_manifest:
        if not isinstance(raw_path, str):
            continue
        blob = _git_blob(root, parent, raw_path)
        if blob is None:
            continue
        baseline_manifest[raw_path] = {
            "size_bytes": len(blob),
            "mtime_ns": 0,
            "sha256": hashlib.sha256(blob).hexdigest(),
        }

    diff = _git_text(root, "diff", "--name-status", "--no-renames", parent, "--")
    if diff:
        for line in diff.splitlines():
            status, separator, raw_path = line.partition("\t")
            if not separator or not status.startswith("D"):
                continue
            if not RepositoryScanner._is_supported_source_file(Path(raw_path)):
                continue
            blob = _git_blob(root, parent, raw_path)
            if blob is not None:
                baseline_manifest[raw_path] = {
                    "size_bytes": len(blob),
                    "mtime_ns": 0,
                    "sha256": hashlib.sha256(blob).hexdigest(),
                }

    baseline_report = _portable_report(current_report)
    baseline_report["file_manifest"] = baseline_manifest
    summary = dict(baseline_report.get("summary", {}))
    summary["source_files_selected"] = len(baseline_manifest)
    summary["inventory_files"] = len(baseline_manifest)
    summary["selected_bytes"] = sum(
        int(value.get("size_bytes", 0))
        for value in baseline_manifest.values()
        if isinstance(value, dict)
    )
    baseline_report["summary"] = summary
    current_report = _portable_report(current_report)

    branch = _git_text(root, "branch", "--show-current")
    dirty = bool(_git_text(root, "status", "--porcelain=v1", "--untracked-files=all"))
    baseline_id = f"baseline-{parent[:12]}"
    current_id = f"current-{head[:12]}"
    snapshots_dir = output / "snapshots"
    baseline_metadata = _write_prepared_snapshot(
        snapshots_dir / baseline_id,
        baseline_id,
        baseline_report,
        commit=parent,
        branch=branch,
        dirty=False,
    )
    _write_json(snapshots_dir / baseline_id / "metadata.json", baseline_metadata)
    current_metadata = _write_prepared_snapshot(
        snapshots_dir / current_id,
        current_id,
        current_report,
        commit=head,
        branch=branch,
        dirty=dirty,
    )
    _write_json(snapshots_dir / current_id / "metadata.json", current_metadata)
    return {"from": baseline_id, "to": current_id}


def _wait_for_index(server: Any, repo: str, timeout_seconds: float) -> dict[str, Any]:
    active = server._index_state().get("active", {}).get(repo)
    if active is None:
        health = server.indexer.index_health()
        if (
            health.get("ready")
            and health.get("repository") == repo
            and isinstance(health.get("generation_id"), str)
        ):
            return health
        server._start_index_repo_job(repo, reason="prepare_demo")
        active = server._index_state().get("active", {}).get(repo)
    job_id = active.get("job_id") if isinstance(active, dict) else None
    if not isinstance(job_id, str):
        raise RuntimeError("Demo indexing job did not start")

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = server.wait_until_ready(
            job_id,
            timeout_seconds=min(5, max(0, deadline - time.monotonic())),
        )
        if result.get("status") in {"completed", "failed", "cancelled", "superseded"}:
            if result.get("status") != "completed":
                raise RuntimeError(result.get("error") or "Demo indexing failed")
            return server.indexer.index_health()
    raise TimeoutError("Demo indexing timed out")


def prepare_demo(
    project: str | Path,
    *,
    demo_dir: str | Path | None = None,
    timeout_seconds: float = 900,
) -> dict[str, Any]:
    """Build demo artifacts and a portable state bundle from the shared runtime."""
    if not 0 < timeout_seconds <= 3600:
        raise ValueError("timeout_seconds must be between 0 and 3600")
    root = Path(project).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Project directory does not exist: {root}")
    output = (Path(demo_dir) if demo_dir is not None else root / "demo").expanduser().resolve()
    if not output.is_relative_to(root):
        raise ValueError("Demo directory must stay inside the project")

    import server

    repo = str(root)
    server.repository_registry.add(repo)
    server.indexer.repos[:] = [repo]
    server.cognitive_runtime.repos[:] = [repo]
    try:
        health = _wait_for_index(server, repo, timeout_seconds)
    finally:
        import city_server

        city_server.stop_watch()
    output.mkdir(parents=True, exist_ok=True)

    artifacts_dir = root / ".agents" / "booster"
    copied = []
    index_artifacts = output / "index_artifacts"
    for name in DEMO_ARTIFACTS:
        source = artifacts_dir / name
        if source.is_file():
            destination = index_artifacts / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if name in {"index_health.json", "scan_report.json", "scan_config.json"}:
                try:
                    payload = json.loads(source.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    payload = None
                if isinstance(payload, dict):
                    payload = dict(payload)
                    payload.pop("repository", None)
                    _write_json(destination, payload)
                else:
                    shutil.copy2(source, destination)
            else:
                shutil.copy2(source, destination)
            copied.append(f"index_artifacts/{name}")

    city = _portable_city(CodeCityVisualizer(server.indexer).generate_city_layout(repo), root)
    _write_json(output / "city.json", city)
    CodeCityVisualizer(server.indexer).generate_html(city, str(output / "code_city.html"))

    repo_map = RepoMap(root=repo, indexer=server.indexer).get_architecture_map()
    _write_json(output / "architecture.json", {"version": 1, "map": repo_map})

    report = {}
    try:
        report = json.loads((artifacts_dir / "scan_report.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    diagnostic_paths = [
        str(root / path) for path in list(report.get("file_manifest", {})) if isinstance(path, str)
    ]
    diagnostics = server.cognitive_runtime.collect_diagnostics(
        diagnostic_paths, repo, False, False, 30
    )
    _write_json(output / "diagnostics.json", _portable_diagnostics(diagnostics, root))
    history_paths = [
        path for path in list(report.get("file_manifest", {})) if isinstance(path, str)
    ]
    _write_json(output / "history.json", _precompute_history(server, root, history_paths))

    source_snapshots = RepositorySnapshotStore(root).list_snapshots(limit=20)
    bundled_snapshots = output / "snapshots"
    for metadata in source_snapshots:
        snapshot_id = metadata.get("snapshot_id")
        raw_snapshot_dir = metadata.get("snapshot_dir")
        if not isinstance(snapshot_id, str) or Path(snapshot_id).name != snapshot_id:
            continue
        if not isinstance(raw_snapshot_dir, str):
            continue
        source_dir = Path(raw_snapshot_dir).expanduser().resolve()
        source_root = (root / ".agents" / "booster" / "snapshots").resolve()
        if not source_dir.is_relative_to(source_root):
            continue
        destination = (bundled_snapshots / snapshot_id).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        for source_file in source_dir.iterdir():
            if source_file.is_file() and source_file.name != "metadata.json":
                shutil.copy2(source_file, destination / source_file.name)
        bundled_metadata = dict(metadata)
        bundled_metadata["repository"] = None
        bundled_metadata["snapshot_dir"] = str(destination)
        bundled_metadata["artifacts"] = {
            name: {
                **value,
                "path": str(destination / name),
            }
            for name, value in metadata.get("artifacts", {}).items()
            if isinstance(value, dict)
        }
        _write_json(destination / "metadata.json", bundled_metadata)
    snapshot_pair = _prepare_snapshot_pair(root, report, output)
    bundled_snapshots = RepositorySnapshotStore(root, artifacts_dir=output).list_snapshots(limit=50)
    if snapshot_pair is None and len(bundled_snapshots) >= 2:
        first_id = bundled_snapshots[1].get("snapshot_id")
        second_id = bundled_snapshots[0].get("snapshot_id")
        if isinstance(first_id, str) and isinstance(second_id, str):
            snapshot_pair = {"from": first_id, "to": second_id}
    if snapshot_pair is None:
        raise RuntimeError(
            "Demo snapshot comparison requires two real snapshots or a Git parent commit"
        )
    _write_json(output / "snapshots.json", [_safe_snapshot(item) for item in bundled_snapshots])
    if bundled_snapshots:
        _write_json(output / "latest.json", bundled_snapshots[0])

    state = server.indexer.save_state(output / "index_state", repo)
    manifest = {
        "version": 1,
        "repo_id": "booster-demo",
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "generation_id": health.get("generation_id"),
        "artifacts": [
            *copied,
            "city.json",
            "code_city.html",
            "architecture.json",
            "diagnostics.json",
            "history.json",
            "snapshots.json",
            "latest.json",
            "snapshots/",
            "index_state/state.json",
            "index_state/vector/index.faiss",
            "index_state/vector/metadata.json",
        ],
        "read_only": True,
        "requires_indexing_on_start": False,
        "requires_embedding_model_on_start": False,
        "snapshot_pair": snapshot_pair,
        "index_state": {
            key: state[key] for key in ("version", "generation_id", "files") if key in state
        },
    }
    _write_json(output / "manifest.json", manifest)
    return manifest
