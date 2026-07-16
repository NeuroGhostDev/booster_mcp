"""Пользовательский командный интерфейс для артефактов репозитория Booster."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from repomap import RepoMap
from repository_scanner import (
    ARTIFACTS_DIRECTORY,
    PROFILE_LIMITS,
    SCAN_CONFIG_FILENAME,
    RepositoryScanner,
    ScanConfig,
)


def _positive_integer(value: str) -> int:
    try:
        parsed_value = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Expected a positive integer.") from exc
    if parsed_value <= 0:
        raise argparse.ArgumentTypeError("Expected a positive integer.")
    return parsed_value


def _format_bytes(size_bytes: int) -> str:
    units = ("B", "KiB", "MiB", "GiB")
    size = float(size_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="booster",
        description="Create bounded Booster repository artifacts from the current directory.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    expand = subcommands.add_parser(
        "expand",
        aliases=["expance"],
        help="Initialize bounded scanning and generate a repository map.",
    )
    expand.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Repository directory. Defaults to the current directory.",
    )
    expand.add_argument(
        "--profile",
        choices=sorted(PROFILE_LIMITS),
        help="Scan budget profile. Defaults to the saved profile or balanced.",
    )
    expand.add_argument(
        "--max-depth",
        type=_positive_integer,
        help="Maximum directory depth to traverse.",
    )
    expand.add_argument(
        "--max-files",
        type=_positive_integer,
        help="Maximum number of supported source files to select.",
    )
    expand.add_argument(
        "--max-file-size-kb",
        type=_positive_integer,
        help="Maximum individual source file size in KiB.",
    )
    expand.add_argument(
        "--max-total-size-mb",
        type=_positive_integer,
        help="Maximum combined size of selected source files in MiB.",
    )
    expand.add_argument(
        "--max-directories",
        type=_positive_integer,
        help="Maximum number of directories to inspect.",
    )
    dependencies = expand.add_mutually_exclusive_group()
    dependencies.add_argument(
        "--include-dependencies",
        action="store_true",
        dest="include_dependencies",
        help="Include vendor and third-party dependency directories.",
    )
    dependencies.add_argument(
        "--exclude-dependencies",
        action="store_false",
        dest="include_dependencies",
        help="Exclude vendor and third-party dependency directories.",
    )
    expand.set_defaults(include_dependencies=None)
    expand.add_argument(
        "--max-tokens",
        type=_positive_integer,
        default=4096,
        help="Approximate token budget for repo_map.md. Defaults to 4096.",
    )
    expand.add_argument(
        "--no-save-config",
        action="store_true",
        help="Do not save the selected scan settings for future MCP indexing.",
    )
    expand.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable summary.",
    )
    return parser


def _resolve_config(arguments: argparse.Namespace, root: Path) -> ScanConfig:
    config_path = root / ARTIFACTS_DIRECTORY / SCAN_CONFIG_FILENAME
    if arguments.profile:
        config = ScanConfig.for_profile(arguments.profile)
    elif config_path.is_file():
        config = ScanConfig.load(root)
    else:
        config = ScanConfig.for_profile()

    return config.with_overrides(
        max_depth=arguments.max_depth,
        max_files=arguments.max_files,
        max_file_bytes=(
            arguments.max_file_size_kb * 1024 if arguments.max_file_size_kb is not None else None
        ),
        max_total_bytes=(
            arguments.max_total_size_mb * 1024 * 1024
            if arguments.max_total_size_mb is not None
            else None
        ),
        max_directories=arguments.max_directories,
        include_dependencies=arguments.include_dependencies,
    )


def _expand(arguments: argparse.Namespace) -> int:
    root = Path(arguments.path).expanduser().resolve()
    if not root.is_dir():
        print(
            f"error: repository directory does not exist: {root}", file=sys.stderr)
        return 2

    config = _resolve_config(arguments, root)
    scan_result = RepositoryScanner(root, config).scan()
    repo_map = RepoMap(root=root, max_tokens=arguments.max_tokens)
    map_content = repo_map.get_repo_map(files=scan_result.files)

    artifact_dir = root / ARTIFACTS_DIRECTORY
    artifact_dir.mkdir(parents=True, exist_ok=True)
    map_path = artifact_dir / "repo_map.md"
    map_path.write_text(map_content, encoding="utf-8")
    report_path = scan_result.save_report()
    config_path = None if arguments.no_save_config else config.save(root)

    summary = {
        "command": "expand",
        "repository": str(root),
        "profile": config.profile,
        "repo_map": str(map_path),
        "scan_report": str(report_path),
        "scan_config": str(config_path) if config_path else None,
        "source_files": len(scan_result.files),
        "selected_bytes": scan_result.selected_bytes,
        "directories_scanned": scan_result.scanned_directories,
        "limits_reached": sorted(scan_result.limits_reached),
        "map_created": bool(map_content),
    }
    if arguments.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("Booster expand")
        print(f"  Repository: {root}")
        print(f"  Profile: {config.profile}")
        print(
            "  Selected: "
            f"{len(scan_result.files)} source files / {_format_bytes(scan_result.selected_bytes)}"
        )
        print(f"  Repo map: {map_path}")
        print(f"  Scan report: {report_path}")
        if config_path:
            print(f"  Saved scan settings: {config_path}")
        if scan_result.limits_reached:
            limits = ", ".join(sorted(scan_result.limits_reached))
            print(f"  Scan budget reached: {limits}")
            print("  Rerun with --profile deep or explicit limits to include more code.")
        if not map_content:
            print("  No supported source definitions were found.", file=sys.stderr)

    return 0 if map_content else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Запускает CLI Booster и возвращает код завершения для shell."""
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command in {"expand", "expance"}:
        return _expand(arguments)
    parser.error(f"Unknown command: {arguments.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
