"""Persistent repository bindings and immutable index snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from file_lock import cross_process_file_lock

REGISTRY_ENV = "BOOSTER_REPOSITORY_REGISTRY"
SNAPSHOT_DIRECTORY = "snapshots"
SNAPSHOT_ARTIFACTS = (
    "repo_map.md",
    "repo_map_architecture.md",
    "repo_map_symbols.md",
    "index_health.json",
    "code_city.html",
    "scan_config.json",
    "scan_report.json",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
    )
    temporary_path = Path(temporary_name)
    try:
        os.close(descriptor)
        shutil.copyfile(source, temporary_path)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RepositoryRegistry:
    """Stores active repository bindings outside an individual MCP process."""

    def __init__(self, root: str | Path | None = None) -> None:
        configured = root or os.getenv(REGISTRY_ENV)
        self.root = (
            Path(configured).expanduser().resolve()
            if configured
            else (Path.home() / ".booster" / "repositories").resolve()
        )
        self._lock = threading.RLock()
        self._file_lock_path = self.root / ".registry.lock"

    @staticmethod
    def normalize(repo_path: str | Path) -> str:
        return str(Path(repo_path).expanduser().resolve())

    @staticmethod
    def _key(repo_path: str) -> str:
        return hashlib.sha256(repo_path.encode("utf-8")).hexdigest()[:32]

    def _record_path(self, repo_path: str) -> Path:
        return self.root / f"{self._key(repo_path)}.json"

    def _read_record(self, path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(value, dict) or not isinstance(value.get("repository"), str):
            return None
        return value

    def list_records(self) -> list[dict[str, Any]]:
        with self._lock:
            with cross_process_file_lock(self._file_lock_path):
                if not self.root.is_dir():
                    return []
                records = [
                    record
                    for path in sorted(self.root.glob("*.json"))
                    if (record := self._read_record(path)) is not None
                ]
        return sorted(
            records,
            key=lambda record: (str(record.get("added_at_utc", "")), record["repository"]),
        )

    def list_repos(self) -> list[str]:
        return [record["repository"] for record in self.list_records()]

    def get(self, repo_path: str | Path) -> dict[str, Any] | None:
        normalized = self.normalize(repo_path)
        with self._lock:
            with cross_process_file_lock(self._file_lock_path):
                return self._read_record(self._record_path(normalized))

    def add(self, repo_path: str | Path) -> dict[str, Any]:
        normalized = self.normalize(repo_path)
        now = _utc_now()
        with self._lock:
            with cross_process_file_lock(self._file_lock_path):
                record = self._read_record(self._record_path(normalized)) or {
                    "version": 1,
                    "repository": normalized,
                    "added_at_utc": now,
                }
                record["updated_at_utc"] = now
                _atomic_write_json(self._record_path(normalized), record)
                return record

    def update(self, repo_path: str | Path, **updates: Any) -> dict[str, Any]:
        normalized = self.normalize(repo_path)
        now = _utc_now()
        with self._lock:
            with cross_process_file_lock(self._file_lock_path):
                record = self._read_record(self._record_path(normalized)) or {
                    "version": 1,
                    "repository": normalized,
                    "added_at_utc": now,
                }
                record.update(updates)
                record["updated_at_utc"] = now
                _atomic_write_json(self._record_path(normalized), record)
                return record

    def remove(self, repo_path: str | Path) -> bool:
        normalized = self.normalize(repo_path)
        with self._lock:
            with cross_process_file_lock(self._file_lock_path):
                path = self._record_path(normalized)
                if not path.exists():
                    return False
                path.unlink()
                return True


class RepositorySnapshotStore:
    """Keeps generated Booster artifacts immutable and points to the latest one."""

    def __init__(self, repo_path: str | Path) -> None:
        self.repo = Path(repo_path).expanduser().resolve()
        self.artifacts_dir = self.repo / ".agents" / "booster"
        self.snapshots_dir = self.artifacts_dir / SNAPSHOT_DIRECTORY
        self._lock = threading.RLock()
        self._file_lock_path = self.artifacts_dir / ".snapshots.lock"

    def _git(self, *arguments: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo), *arguments],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None

    def _git_state(self) -> dict[str, Any]:
        commit = self._git("rev-parse", "HEAD") or "NO_COMMIT"
        status = self._git("status", "--porcelain=v1", "--untracked-files=all") or ""
        return {
            "commit": commit,
            "commit_short": commit[:12] if commit != "NO_COMMIT" else "NO_COMMIT",
            "branch": self._git("branch", "--show-current"),
            "dirty": bool(status),
            "status_digest": hashlib.sha256(status.encode("utf-8")).hexdigest()[:16],
        }

    def _artifact_digest(self, paths: dict[str, Path]) -> str:
        digest = hashlib.sha256()
        for name in SNAPSHOT_ARTIFACTS:
            digest.update(name.encode("utf-8"))
            path = paths[name]
            if not path.is_file():
                digest.update(b"<missing>")
                continue
            if name == "scan_report.json":
                try:
                    report = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    report = None
                if isinstance(report, dict):
                    report.pop("generated_at_utc", None)
                    digest.update(
                        json.dumps(report, ensure_ascii=False, sort_keys=True).encode("utf-8")
                    )
                    continue
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        return digest.hexdigest()

    def capture(
        self,
        *,
        task_id: str | None = None,
        reason: str | None = None,
        indexed_files: int | None = None,
    ) -> dict[str, Any]:
        """Captures generated artifacts without deleting or replacing history."""
        with self._lock:
            with cross_process_file_lock(self._file_lock_path):
                self.artifacts_dir.mkdir(parents=True, exist_ok=True)
                paths = {name: self.artifacts_dir / name for name in SNAPSHOT_ARTIFACTS}
                git_state = self._git_state()
                artifact_digest = self._artifact_digest(paths)
                commit_token = (
                    git_state["commit_short"].lower()
                    if git_state["commit"] != "NO_COMMIT"
                    else "no-commit"
                )
                state_token = "dirty" if git_state["dirty"] else "clean"
                snapshot_id = f"{commit_token}-{state_token}-{artifact_digest[:16]}"
                snapshot_dir = self.snapshots_dir / snapshot_id
                snapshot_dir.mkdir(parents=True, exist_ok=True)

                artifacts: dict[str, dict[str, Any]] = {}
                for name, source in paths.items():
                    if not source.is_file():
                        continue
                    destination = snapshot_dir / name
                    if not destination.exists():
                        _atomic_copy(source, destination)
                    artifacts[name] = {
                        "path": str(destination),
                        "size_bytes": destination.stat().st_size,
                        "sha256": _sha256_file(destination),
                    }

                metadata = {
                    "version": 1,
                    "snapshot_id": snapshot_id,
                    "repository": str(self.repo),
                    "captured_at_utc": _utc_now(),
                    "commit": git_state["commit"],
                    "commit_short": git_state["commit_short"],
                    "branch": git_state["branch"],
                    "dirty": git_state["dirty"],
                    "status_digest": git_state["status_digest"],
                    "artifact_digest": artifact_digest,
                    "snapshot_dir": str(snapshot_dir),
                    "artifacts": artifacts,
                    "indexed_files": indexed_files,
                    "task_id": task_id,
                    "reason": reason,
                    "previous_snapshots_preserved": True,
                }
                metadata_path = snapshot_dir / "metadata.json"
                if not metadata_path.exists():
                    _atomic_write_json(metadata_path, metadata)

                latest_path = self.artifacts_dir / "latest.json"
                _atomic_write_json(latest_path, metadata)
                return metadata

    def latest(self) -> dict[str, Any] | None:
        with self._lock:
            with cross_process_file_lock(self._file_lock_path):
                path = self.artifacts_dir / "latest.json"
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    return None
                return value if isinstance(value, dict) else None

    def list_snapshots(self, limit: int = 20) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        with self._lock:
            with cross_process_file_lock(self._file_lock_path):
                records: list[dict[str, Any]] = []
                for path in sorted(
                    self.snapshots_dir.glob("*/metadata.json"),
                    key=lambda item: item.stat().st_mtime,
                    reverse=True,
                ):
                    try:
                        value = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if isinstance(value, dict):
                        records.append(value)
                    if len(records) >= limit:
                        break
                return records


__all__ = ["RepositoryRegistry", "RepositorySnapshotStore"]
