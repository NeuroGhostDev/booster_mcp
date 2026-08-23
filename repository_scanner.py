"""Ограниченное и детерминированное обнаружение исходников для Booster."""

from __future__ import annotations

import fnmatch
import json
import os
from collections import Counter, deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from grep_ast import filename_to_lang

ARTIFACTS_DIRECTORY = Path(".agents") / "booster"
SCAN_CONFIG_FILENAME = "scan_config.json"
SCAN_REPORT_FILENAME = "scan_report.json"

PROFILE_LIMITS: dict[str, dict[str, int]] = {
    "quick": {
        "max_depth": 6,
        "max_files": 250,
        "max_file_bytes": 256 * 1024,
        "max_total_bytes": 8 * 1024 * 1024,
        "max_directories": 1_000,
    },
    "balanced": {
        "max_depth": 12,
        "max_files": 800,
        "max_file_bytes": 1 * 1024 * 1024,
        "max_total_bytes": 32 * 1024 * 1024,
        "max_directories": 5_000,
    },
    "deep": {
        "max_depth": 20,
        "max_files": 3_000,
        "max_file_bytes": 2 * 1024 * 1024,
        "max_total_bytes": 128 * 1024 * 1024,
        "max_directories": 15_000,
    },
}

STANDARD_IGNORED_DIRECTORIES = frozenset(
    {
        ".agents",
        ".cache",
        ".git",
        ".gradle",
        ".hg",
        ".idea",
        ".mypy_cache",
        ".next",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".terraform",
        ".tox",
        ".venv",
        ".vs",
        ".vscode",
        "__pycache__",
        "bin",
        "build",
        "coverage",
        "dist",
        "env",
        "logs",
        "obj",
        "out",
        "target",
        "temp",
        "tmp",
        "venv",
    }
)
DEPENDENCY_DIRECTORIES = frozenset(
    {
        "bower_components",
        "deriveddata",
        "node_modules",
        "pods",
        "third_party",
        "third-party",
        "vendor",
    }
)
DIRECTORY_PRIORITIES = {
    "src": 0,
    "app": 0,
    "apps": 1,
    "api": 1,
    "backend": 1,
    "cmd": 1,
    "core": 1,
    "frontend": 1,
    "internal": 1,
    "lib": 1,
    "packages": 1,
    "services": 1,
    "tests": 3,
    "test": 3,
    "examples": 4,
    "docs": 5,
}


@dataclass(frozen=True)
class ScanConfig:
    """Лимиты, делающие обход больших репозиториев предсказуемым."""

    profile: str
    max_depth: int
    max_files: int
    max_file_bytes: int
    max_total_bytes: int
    max_directories: int
    include_dependencies: bool = False

    def __post_init__(self) -> None:
        for value in (
            self.max_depth,
            self.max_files,
            self.max_file_bytes,
            self.max_total_bytes,
            self.max_directories,
        ):
            if value <= 0:
                raise ValueError("Scan limits must be greater than zero.")

    @classmethod
    def for_profile(cls, profile: str = "balanced") -> "ScanConfig":
        try:
            return cls(profile=profile, **PROFILE_LIMITS[profile])
        except KeyError as exc:
            available_profiles = ", ".join(sorted(PROFILE_LIMITS))
            raise ValueError(
                f"Unknown scan profile '{profile}'. Available profiles: {available_profiles}."
            ) from exc

    @classmethod
    def load(cls, root: str | Path) -> "ScanConfig":
        root_path = Path(root).expanduser().resolve()
        config_path = root_path / ARTIFACTS_DIRECTORY / SCAN_CONFIG_FILENAME
        if not config_path.is_file():
            return cls.for_profile()

        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls.for_profile()

        profile = payload.get("profile", "balanced")
        try:
            base_config = cls.for_profile(profile)
        except ValueError:
            base_config = cls.for_profile()

        limits = payload.get("limits", {})
        overrides: dict[str, Any] = {
            "include_dependencies": payload.get(
                "include_dependencies", base_config.include_dependencies
            )
        }
        for field_name in (
            "max_depth",
            "max_files",
            "max_file_bytes",
            "max_total_bytes",
            "max_directories",
        ):
            value = limits.get(field_name)
            if isinstance(value, int) and value > 0:
                overrides[field_name] = value

        return replace(base_config, **overrides)

    def with_overrides(self, **overrides: Any) -> "ScanConfig":
        values = {name: value for name, value in overrides.items()
                  if value is not None}
        return replace(self, **values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "profile": self.profile,
            "include_dependencies": self.include_dependencies,
            "limits": {
                "max_depth": self.max_depth,
                "max_files": self.max_files,
                "max_file_bytes": self.max_file_bytes,
                "max_total_bytes": self.max_total_bytes,
                "max_directories": self.max_directories,
            },
        }

    def save(self, root: str | Path) -> Path:
        artifact_dir = Path(root).expanduser().resolve() / ARTIFACTS_DIRECTORY
        artifact_dir.mkdir(parents=True, exist_ok=True)
        config_path = artifact_dir / SCAN_CONFIG_FILENAME
        config_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return config_path


@dataclass(frozen=True)
class IgnoreRules:
    """Правила директорий, файлов и glob-паттернов из ignore-файлов проекта."""

    directories: frozenset[str]
    filenames: frozenset[str]
    patterns: tuple[str, ...]

    @classmethod
    def from_repository(cls, root: Path, config: ScanConfig) -> "IgnoreRules":
        directories = set(STANDARD_IGNORED_DIRECTORIES)
        if not config.include_dependencies:
            directories.update(DEPENDENCY_DIRECTORIES)

        filenames: set[str] = set()
        patterns: list[str] = []
        ignore_paths = (
            Path.home() / ".ignore",
            root / ".ignore",
            root / ".boosterignore",
        )
        for ignore_path in dict.fromkeys(ignore_paths):
            if not ignore_path.is_file():
                continue
            try:
                lines = ignore_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue

            for raw_line in lines:
                rule = raw_line.strip()
                if not rule or rule.startswith("#") or rule.startswith("!"):
                    continue

                normalized = rule.replace("\\", "/").lstrip("/")
                if normalized.endswith("/"):
                    directories.add(normalized.rstrip("/").split("/")[-1])
                elif "/" in normalized or any(token in normalized for token in "*?["):
                    patterns.append(normalized)
                elif "." in normalized:
                    filenames.add(normalized)
                else:
                    directories.add(normalized)

        return cls(
            directories=frozenset(directories),
            filenames=frozenset(filenames),
            patterns=tuple(patterns),
        )

    def ignores_directory(self, name: str, relative_path: str) -> bool:
        return name in self.directories or self._matches_pattern(name, relative_path)

    def ignores_file(self, name: str, relative_path: str) -> bool:
        return name in self.filenames or self._matches_pattern(name, relative_path)

    def _matches_pattern(self, name: str, relative_path: str) -> bool:
        for pattern in self.patterns:
            if pattern.endswith("/**"):
                directory_prefix = pattern.removesuffix("/**")
                if relative_path == directory_prefix or relative_path.startswith(
                    f"{directory_prefix}/"
                ):
                    return True
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(relative_path, pattern):
                return True
        return False


@dataclass
class ScanResult:
    """Отобранные исходники и телеметрия, объясняющая решения scanner-а."""

    root: Path
    config: ScanConfig
    files: list[Path]
    scanned_directories: int
    inspected_files: int
    selected_bytes: int
    skipped: Counter[str]
    limits_reached: set[str]
    file_manifest: dict[str, dict[str, int]] = field(default_factory=dict)
    inventory_files: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "repository": str(self.root),
            "profile": self.config.profile,
            "limits": self.config.to_dict()["limits"],
            "include_dependencies": self.config.include_dependencies,
            "summary": {
                "directories_scanned": self.scanned_directories,
                "files_inspected": self.inspected_files,
                "source_files_selected": len(self.files),
                "selected_bytes": self.selected_bytes,
                "inventory_files": self.inventory_files or len(self.files),
            },
            "file_manifest": self.file_manifest,
            "skipped": dict(sorted(self.skipped.items())),
            "limits_reached": sorted(self.limits_reached),
            "sample_files": [path.relative_to(self.root).as_posix() for path in self.files[:50]],
        }

    def save_report(self) -> Path:
        artifact_dir = self.root / ARTIFACTS_DIRECTORY
        artifact_dir.mkdir(parents=True, exist_ok=True)
        report_path = artifact_dir / SCAN_REPORT_FILENAME
        report_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return report_path


class RepositoryScanner:
    """Находит поддерживаемые исходники без полного истощающего обхода репозитория."""

    def __init__(self, root: str | Path, config: ScanConfig | None = None):
        self.root = Path(root).expanduser().resolve()
        self.config = config or ScanConfig.load(self.root)
        self.ignore_rules = IgnoreRules.from_repository(self.root, self.config)

    def scan(
        self,
        progress: Callable[[str, int, int | None], None] | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> ScanResult:
        if not self.root.is_dir():
            raise NotADirectoryError(
                f"Repository directory does not exist: {self.root}")

        files: list[Path] = []
        skipped: Counter[str] = Counter()
        limits_reached: set[str] = set()
        file_manifest: dict[str, dict[str, int]] = {}
        scanned_directories = 0
        inspected_files = 0
        selected_bytes = 0
        inventory_files = 0
        directories: deque[tuple[Path, int]] = deque([(self.root, 0)])

        while directories:
            if cancel is not None and cancel():
                limits_reached.add("cancelled")
                break
            if scanned_directories >= self.config.max_directories:
                limits_reached.add("max_directories")
                break

            directory, depth = directories.popleft()
            scanned_directories += 1
            if progress is not None:
                progress("scan", scanned_directories, self.config.max_directories)
            try:
                entries = list(os.scandir(directory))
            except OSError:
                skipped["unreadable_directory"] += 1
                continue

            child_directories = []
            file_entries = []
            for entry in entries:
                try:
                    if entry.is_symlink():
                        skipped["symlink"] += 1
                    elif entry.is_dir(follow_symlinks=False):
                        child_directories.append(entry)
                    elif entry.is_file(follow_symlinks=False):
                        file_entries.append(entry)
                except OSError:
                    skipped["unreadable_entry"] += 1

            for entry in sorted(child_directories, key=self._directory_sort_key):
                relative_path = self._relative_path(Path(entry.path))
                if entry.name.startswith(".") or self.ignore_rules.ignores_directory(
                    entry.name, relative_path
                ):
                    skipped["ignored_directory"] += 1
                    continue
                if depth + 1 > self.config.max_depth:
                    skipped["max_depth"] += 1
                    limits_reached.add("max_depth")
                    continue
                directories.append((Path(entry.path), depth + 1))

            for entry in sorted(file_entries, key=lambda item: item.name.casefold()):
                if cancel is not None and cancel():
                    limits_reached.add("cancelled")
                    break

                inspected_files += 1
                path = Path(entry.path)
                relative_path = self._relative_path(path)
                if entry.name.startswith(".") or self.ignore_rules.ignores_file(
                    entry.name, relative_path
                ):
                    skipped["ignored_file"] += 1
                    continue
                try:
                    size_bytes = entry.stat(follow_symlinks=False).st_size
                except OSError:
                    skipped["unreadable_file"] += 1
                    continue
                if not self._is_supported_source_file(path):
                    skipped["unsupported_file"] += 1
                    continue

                inventory_files += 1
                try:
                    file_stat = entry.stat(follow_symlinks=False)
                    file_manifest[self._relative_path(path)] = {
                        "size_bytes": int(size_bytes),
                        "mtime_ns": int(file_stat.st_mtime_ns),
                    }
                except OSError:
                    skipped["unreadable_file"] += 1
                    continue

                if len(files) >= self.config.max_files:
                    skipped["max_files"] += 1
                    limits_reached.add("max_files")
                    continue
                if size_bytes > self.config.max_file_bytes:
                    skipped["max_file_bytes"] += 1
                    continue
                if selected_bytes + size_bytes > self.config.max_total_bytes:
                    skipped["max_total_bytes"] += 1
                    limits_reached.add("max_total_bytes")
                    continue

                files.append(path)
                selected_bytes += size_bytes

        return self._result(
            files,
            scanned_directories,
            inspected_files,
            selected_bytes,
            skipped,
            limits_reached,
            file_manifest,
            inventory_files,
        )

    def _result(
        self,
        files: list[Path],
        scanned_directories: int,
        inspected_files: int,
        selected_bytes: int,
        skipped: Counter[str],
        limits_reached: set[str],
        file_manifest: dict[str, dict[str, int]] | None = None,
        inventory_files: int = 0,
    ) -> ScanResult:
        return ScanResult(
            root=self.root,
            config=self.config,
            files=files,
            scanned_directories=scanned_directories,
            inspected_files=inspected_files,
            selected_bytes=selected_bytes,
            skipped=skipped,
            limits_reached=limits_reached,
            file_manifest=file_manifest or {},
            inventory_files=inventory_files,
        )

    def _directory_sort_key(self, entry: os.DirEntry[str]) -> tuple[int, str]:
        name = entry.name.casefold()
        return DIRECTORY_PRIORITIES.get(name, 2), name

    def _relative_path(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    @staticmethod
    def _is_supported_source_file(path: Path) -> bool:
        try:
            return filename_to_lang(str(path)) is not None
        except Exception:
            return False
