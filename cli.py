"""Пользовательский командный интерфейс для артефактов репозитория Booster."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from control import (
    ControlError,
    artifact_status,
    build_server_definition,
    connect,
    connection_status,
    disconnect,
    doctor,
    install_launcher,
    resolve_project,
    runtime_info,
    scan_settings,
    update_scan_settings,
)
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

    control = subcommands.add_parser(
        "control",
        help="Connect MCP clients and manage Booster settings.",
        description=(
            "Manage Booster MCP connections, bounded scan settings, "
            "artifacts, and the local launcher."
        ),
    )
    control.add_argument(
        "--project",
        dest="menu_project",
        default=".",
        help="Repository used by the interactive menu. Defaults to the current directory.",
    )
    control_subcommands = control.add_subparsers(dest="control_command")

    status = control_subcommands.add_parser(
        "status", help="Show MCP connection, scan, and artifact status."
    )
    _add_connection_arguments(status)
    status.add_argument("--json", action="store_true",
                        help="Print JSON output.")

    connect_parser = control_subcommands.add_parser(
        "connect", help="Register Booster in an MCP client configuration."
    )
    _add_connection_arguments(connect_parser)
    _add_repository_binding_arguments(connect_parser)
    connect_parser.add_argument(
        "--force",
        action="store_true",
        help="Replace only an existing server entry with the same name.",
    )
    connect_parser.add_argument(
        "--json", action="store_true", help="Print JSON output.")

    disconnect_parser = control_subcommands.add_parser(
        "disconnect", help="Remove a Booster entry from an MCP client configuration."
    )
    _add_connection_arguments(disconnect_parser)
    disconnect_parser.add_argument(
        "--json", action="store_true", help="Print JSON output."
    )

    preview = control_subcommands.add_parser(
        "preview", help="Print the MCP server entry without changing any file."
    )
    preview.add_argument(
        "--client", choices=("vscode", "claude"), default="vscode", help="MCP client format."
    )
    preview.add_argument(
        "--project", default=".", help="Repository available through REPOS."
    )
    preview.add_argument("--json", action="store_true",
                         help="Print JSON output.")

    scan = control_subcommands.add_parser(
        "scan", help="View or save bounded scan settings for a repository."
    )
    scan.add_argument("--project", default=".", help="Repository directory.")
    scan.add_argument("--profile", choices=sorted(PROFILE_LIMITS),
                      help="Scan budget profile.")
    scan.add_argument("--max-depth", type=_positive_integer,
                      help="Maximum directory depth.")
    scan.add_argument("--max-files", type=_positive_integer,
                      help="Maximum source files.")
    scan.add_argument(
        "--max-file-size-kb", type=_positive_integer, help="Maximum source file size in KiB."
    )
    scan.add_argument(
        "--max-total-size-mb", type=_positive_integer, help="Maximum combined size in MiB."
    )
    scan.add_argument(
        "--max-directories", type=_positive_integer, help="Maximum inspected directories."
    )
    scan_dependencies = scan.add_mutually_exclusive_group()
    scan_dependencies.add_argument(
        "--include-dependencies",
        action="store_true",
        dest="include_dependencies",
        help="Include dependency directories.",
    )
    scan_dependencies.add_argument(
        "--exclude-dependencies",
        action="store_false",
        dest="include_dependencies",
        help="Exclude dependency directories.",
    )
    scan.set_defaults(include_dependencies=None)
    scan.add_argument("--json", action="store_true", help="Print JSON output.")

    doctor_parser = control_subcommands.add_parser(
        "doctor", help="Check the installed runtime and required dependencies."
    )
    doctor_parser.add_argument(
        "--project", default=".", help="Repository directory.")
    doctor_parser.add_argument(
        "--json", action="store_true", help="Print JSON output.")

    launcher = control_subcommands.add_parser(
        "launcher", help="Install or update the user-level booster command."
    )
    launcher.add_argument(
        "--force", action="store_true", help="Replace an unrelated existing launcher."
    )
    launcher.add_argument("--json", action="store_true",
                          help="Print JSON output.")
    return parser


def _add_connection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--client", choices=("vscode", "claude"), default="vscode", help="MCP client."
    )
    parser.add_argument(
        "--scope",
        choices=("workspace", "user"),
        default="workspace",
        help="Configuration scope. Claude Desktop supports only user.",
    )
    parser.add_argument("--project", default=".", help="Repository directory.")
    parser.add_argument(
        "--name", help="MCP server name. Uses a scope-specific default.")


def _add_repository_binding_arguments(parser: argparse.ArgumentParser) -> None:
    bindings = parser.add_mutually_exclusive_group()
    bindings.add_argument(
        "--with-repository",
        action="store_true",
        dest="bind_repository",
        help="Start Booster with REPOS set to --project.",
    )
    bindings.add_argument(
        "--without-repository",
        action="store_false",
        dest="bind_repository",
        help="Start Booster without a fixed repository.",
    )
    parser.set_defaults(bind_repository=None)


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


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _control_status(project: str | Path, client: str, scope: str, name: str | None) -> dict:
    root = resolve_project(project)
    return {
        "runtime": runtime_info(),
        "repository": str(root),
        "connection": connection_status(client, scope, root, name=name),
        "scan": scan_settings(root),
        "artifacts": artifact_status(root),
    }


def _print_control_status(status: dict, as_json: bool = False) -> None:
    if as_json:
        _print_json(status)
        return

    connection = status["connection"]
    scan = status["scan"]
    print("Booster control status")
    print(f"  Repository: {status['repository']}")
    print(f"  Python: {status['runtime']['python']}")
    print(f"  Server: {status['runtime']['server']}")
    print(
        "  Connection: "
        f"{connection['client']} / {connection['scope']} / {connection['server_name']}"
    )
    print(f"  Config: {connection['config_path']}")
    print(f"  Configured: {'yes' if connection['configured'] else 'no'}")
    if connection.get("error"):
        print(f"  Config error: {connection['error']}")
    print(
        f"  Scan profile: {scan['profile']} ({'saved' if scan['saved'] else 'default'})")
    print(
        "  Scan limits: "
        f"depth={scan['limits']['max_depth']}, files={scan['limits']['max_files']}, "
        f"total={_format_bytes(scan['limits']['max_total_bytes'])}"
    )
    print("  Artifacts:")
    for name, artifact in status["artifacts"].items():
        state = "ready" if artifact["exists"] else "missing"
        print(f"    {name}: {state}")


def _print_connection_result(result: dict, action: str, as_json: bool = False) -> None:
    if as_json:
        _print_json(result)
        return

    if result["updated"]:
        verb = "Connected" if action == "connect" else "Disconnected"
        print(f"{verb} {result['server_name']} in {result['config_path']}")
        if result.get("backup_path"):
            print(f"  Backup: {result['backup_path']}")
    else:
        print(f"No change: {result['reason']} ({result['config_path']})")


def _print_scan_result(result: dict, as_json: bool = False) -> None:
    if as_json:
        _print_json(result)
        return
    limits = result["limits"]
    print(f"Saved scan settings: {result['config_path']}")
    print(f"  Profile: {result['profile']}")
    print(
        "  Limits: "
        f"depth={limits['max_depth']}, files={limits['max_files']}, "
        f"file={_format_bytes(limits['max_file_bytes'])}, "
        f"total={_format_bytes(limits['max_total_bytes'])}, "
        f"directories={limits['max_directories']}"
    )
    print(
        f"  Include dependencies: {'yes' if result['include_dependencies'] else 'no'}")


def _print_doctor_result(result: dict, as_json: bool = False) -> None:
    if as_json:
        _print_json(result)
        return
    print(f"Booster doctor: {'healthy' if result['ok'] else 'failed'}")
    for check in result["checks"]:
        state = "ok" if check["ok"] else "missing"
        print(f"  {check['name']}: {state} ({check['value']})")


def _run_control_menu(project: str | Path) -> int:
    try:
        root = resolve_project(project)
    except ControlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    while True:
        print()
        print("Booster control")
        print(f"Repository: {root}")
        print("  1. Show VS Code workspace status")
        print("  2. Connect VS Code workspace")
        print("  3. Connect VS Code user profile")
        print("  4. Connect Claude Desktop user profile")
        print("  5. Change bounded scan profile")
        print("  6. Refresh repository artifacts")
        print("  7. Run runtime doctor")
        print("  8. Disconnect an MCP client")
        print("  9. Install or update the booster launcher")
        print("  0. Exit")
        choice = input("Select an action: ").strip()
        try:
            if choice == "0":
                return 0
            if choice == "1":
                _print_control_status(_control_status(
                    root, "vscode", "workspace", None))
            elif choice in {"2", "3", "4"}:
                client, scope = {
                    "2": ("vscode", "workspace"),
                    "3": ("vscode", "user"),
                    "4": ("claude", "user"),
                }[choice]
                try:
                    result = connect(client, scope, root)
                except ControlError as exc:
                    if "Use --force" not in str(exc):
                        raise
                    replace = input(
                        "Replace the existing entry? [y/N]: ").strip().lower()
                    if replace not in {"y", "yes"}:
                        print("Connection unchanged.")
                        continue
                    result = connect(client, scope, root, force=True)
                _print_connection_result(result, "connect")
            elif choice == "5":
                profile = input(
                    "Profile (quick, balanced, deep): ").strip().lower()
                if profile not in PROFILE_LIMITS:
                    print("Unknown profile. Settings unchanged.")
                    continue
                dependencies = input(
                    "Include dependency directories? [y/N]: ").strip().lower()
                result = update_scan_settings(
                    root,
                    profile=profile,
                    include_dependencies=dependencies in {"y", "yes"},
                )
                _print_scan_result(result)
            elif choice == "6":
                _expand(
                    argparse.Namespace(
                        path=str(root),
                        profile=None,
                        max_depth=None,
                        max_files=None,
                        max_file_size_kb=None,
                        max_total_size_mb=None,
                        max_directories=None,
                        include_dependencies=None,
                        max_tokens=4096,
                        no_save_config=False,
                        json=False,
                    )
                )
            elif choice == "7":
                _print_doctor_result(doctor(root))
            elif choice == "8":
                client = input("Client (vscode, claude): ").strip().lower()
                scope = "user" if client == "claude" else input(
                    "Scope (workspace, user): "
                ).strip().lower()
                _print_connection_result(disconnect(
                    client, scope, root), "disconnect")
            elif choice == "9":
                result = install_launcher()
                print(f"Launcher: {result['launcher_path']}")
                if not result.get("path_on_environment", False):
                    print(
                        f"Add {result['user_bin']} to PATH, then open a new terminal.")
            else:
                print("Unknown selection.")
        except ControlError as exc:
            print(f"error: {exc}", file=sys.stderr)


def _control(arguments: argparse.Namespace) -> int:
    command = arguments.control_command
    if command is None:
        return _run_control_menu(arguments.menu_project)

    try:
        if command == "status":
            _print_control_status(
                _control_status(
                    arguments.project,
                    arguments.client,
                    arguments.scope,
                    arguments.name,
                ),
                arguments.json,
            )
            return 0
        if command == "connect":
            result = connect(
                arguments.client,
                arguments.scope,
                arguments.project,
                name=arguments.name,
                force=arguments.force,
                bind_repository=arguments.bind_repository,
            )
            _print_connection_result(result, "connect", arguments.json)
            return 0
        if command == "disconnect":
            result = disconnect(
                arguments.client,
                arguments.scope,
                arguments.project,
                name=arguments.name,
            )
            _print_connection_result(result, "disconnect", arguments.json)
            return 0
        if command == "preview":
            definition = build_server_definition(
                arguments.client, arguments.project)
            if arguments.json:
                _print_json(definition)
            else:
                _print_json(definition)
            return 0
        if command == "scan":
            has_changes = any(
                value is not None
                for value in (
                    arguments.profile,
                    arguments.include_dependencies,
                    arguments.max_depth,
                    arguments.max_files,
                    arguments.max_file_size_kb,
                    arguments.max_total_size_mb,
                    arguments.max_directories,
                )
            )
            if not has_changes:
                result = scan_settings(arguments.project)
                if arguments.json:
                    _print_json(result)
                else:
                    _print_scan_result(result)
                return 0
            result = update_scan_settings(
                arguments.project,
                profile=arguments.profile,
                include_dependencies=arguments.include_dependencies,
                max_depth=arguments.max_depth,
                max_files=arguments.max_files,
                max_file_bytes=(
                    arguments.max_file_size_kb * 1024
                    if arguments.max_file_size_kb is not None
                    else None
                ),
                max_total_bytes=(
                    arguments.max_total_size_mb * 1024 * 1024
                    if arguments.max_total_size_mb is not None
                    else None
                ),
                max_directories=arguments.max_directories,
            )
            _print_scan_result(result, arguments.json)
            return 0
        if command == "doctor":
            result = doctor(arguments.project)
            _print_doctor_result(result, arguments.json)
            return 0 if result["ok"] else 1
        if command == "launcher":
            result = install_launcher(force=arguments.force)
            if arguments.json:
                _print_json(result)
            else:
                print(f"Launcher: {result['launcher_path']}")
                if not result.get("path_on_environment", False):
                    print(
                        f"Add {result['user_bin']} to PATH, then open a new terminal.")
            return 0
    except ControlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"error: unknown control command: {command}", file=sys.stderr)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    """Запускает CLI Booster и возвращает код завершения для shell."""
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command in {"expand", "expance"}:
        return _expand(arguments)
    if arguments.command == "control":
        return _control(arguments)
    parser.error(f"Unknown command: {arguments.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
