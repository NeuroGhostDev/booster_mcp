"""Пользовательский командный интерфейс для артефактов репозитория Booster."""

from __future__ import annotations

import argparse
import asyncio
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
        raise argparse.ArgumentTypeError("Expected a positive integer.") from exc
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


def _context_window(value: str) -> int | str:
    if value.lower() == "auto":
        return "auto"
    return _positive_integer(value)


def _worker_count(value: str) -> int | str:
    if value.lower() == "auto":
        return "auto"
    return _positive_integer(value)


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

    web = subcommands.add_parser(
        "web",
        help="Run the read-only Booster Observatory web gateway.",
        description="Serve the browser workspace over the shared Booster runtime.",
    )
    web.add_argument("--project", default=".", help="Known repository directory.")
    web.add_argument("--host", default="127.0.0.1", help="Bind address.")
    web.add_argument("--port", type=_positive_integer, default=8000, help="Bind port.")
    web.add_argument("--mode", choices=("local", "demo"), default="local")
    web.add_argument("--demo-dir", default=None, help="Prepared demo bundle directory.")
    web_subcommands = web.add_subparsers(dest="web_command")
    prepare_demo = web_subcommands.add_parser(
        "prepare-demo", help="Build a portable read-only Observatory demo bundle."
    )
    prepare_demo.add_argument("--project", default=".", help="Repository to prepare.")
    prepare_demo.add_argument("--demo-dir", default=None, help="Output demo directory.")
    prepare_demo.add_argument(
        "--timeout-seconds", type=float, default=900, help="Maximum indexing time."
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
    status.add_argument("--json", action="store_true", help="Print JSON output.")

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
    connect_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    disconnect_parser = control_subcommands.add_parser(
        "disconnect", help="Remove a Booster entry from an MCP client configuration."
    )
    _add_connection_arguments(disconnect_parser)
    disconnect_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    preview = control_subcommands.add_parser(
        "preview", help="Print the MCP server entry without changing any file."
    )
    preview.add_argument(
        "--client", choices=("vscode", "claude"), default="vscode", help="MCP client format."
    )
    preview.add_argument("--project", default=".", help="Repository available through REPOS.")
    preview.add_argument("--json", action="store_true", help="Print JSON output.")

    scan = control_subcommands.add_parser(
        "scan", help="View or save bounded scan settings for a repository."
    )
    scan.add_argument("--project", default=".", help="Repository directory.")
    scan.add_argument("--profile", choices=sorted(PROFILE_LIMITS), help="Scan budget profile.")
    scan.add_argument("--max-depth", type=_positive_integer, help="Maximum directory depth.")
    scan.add_argument("--max-files", type=_positive_integer, help="Maximum source files.")
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
    doctor_parser.add_argument("--project", default=".", help="Repository directory.")
    doctor_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    launcher = control_subcommands.add_parser(
        "launcher", help="Install or update the user-level booster command."
    )
    launcher.add_argument(
        "--force", action="store_true", help="Replace an unrelated existing launcher."
    )
    launcher.add_argument("--json", action="store_true", help="Print JSON output.")

    home = subcommands.add_parser(
        "home",
        help="Запустить Booster Home OpenAI-compatible gateway.",
        description="Локальный data plane с context compiler, session memory и streaming.",
    )
    home.add_argument("--base-url", dest="base_url", help="URL OpenAI-compatible upstream.")
    home.add_argument("--model", help="Основная upstream/worker model.")
    home.add_argument("--api-key", help="API key upstream; не выводится в status/logs.")
    home.add_argument(
        "--auth-token",
        help="Bearer token для non-loopback Home bind; не выводится в status/logs.",
    )
    home.add_argument("--listen", default=None, help="Адрес bind gateway. По умолчанию 127.0.0.1.")
    home.add_argument("--port", type=_positive_integer, help="Порт gateway.")
    home.add_argument(
        "--context-window", type=_context_window, help="Размер context window или auto."
    )
    home.add_argument("--reserve-output", type=_positive_integer, help="Резерв output tokens.")
    home.add_argument("--workers", type=_worker_count, help="Число semantic workers или auto.")
    home.add_argument("--project", default=None, help="Репозиторий для world-model integration.")
    home.add_argument(
        "--context-policy",
        choices=("off", "safe", "adaptive", "aggressive"),
        help="Политика compiler.",
    )
    home.add_argument("--config", dest="home_config", help="Явный TOML config.")
    home.add_argument("--verbose", action="store_true", default=None, help="Подробные логи.")
    home.add_argument("--json-logs", action="store_true", default=None, help="JSON logs.")
    home.add_argument(
        "--no-persist",
        action="store_true",
        default=None,
        help="Отключить persistence; hard overflow fail-closed.",
    )
    home.add_argument(
        "--probe-generation",
        action="store_true",
        default=None,
        help="Проверить generation при doctor.",
    )
    home_subcommands = home.add_subparsers(dest="home_command")
    home_status = home_subcommands.add_parser(
        "status", help="Показать состояние Home без запуска gateway."
    )
    home_status.add_argument("--json", action="store_true", help="JSON output.")
    home_doctor = home_subcommands.add_parser(
        "doctor", help="Проверить конфигурацию и окружение Home."
    )
    home_doctor.add_argument("--json", action="store_true", help="JSON output.")
    inspect_context = home_subcommands.add_parser(
        "inspect-context", help="Скомпилировать JSON request без отправки upstream."
    )
    inspect_context.add_argument(
        "--input", dest="input_path", help="JSON-файл Chat Completions request."
    )
    inspect_context.add_argument("--json", action="store_true", help="JSON output.")
    sessions = home_subcommands.add_parser("sessions", help="Управление session storage.")
    sessions_subcommands = sessions.add_subparsers(dest="sessions_command", required=True)
    sessions_delete = sessions_subcommands.add_parser(
        "delete", help="Удалить только указанную session."
    )
    sessions_delete.add_argument("session_id")
    sessions_delete.add_argument("--json", action="store_true", help="JSON output.")
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
    parser.add_argument("--name", help="MCP server name. Uses a scope-specific default.")


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
        print(f"error: repository directory does not exist: {root}", file=sys.stderr)
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


def _web(arguments: argparse.Namespace) -> int:
    """Runs the same-origin read-only Observatory gateway."""
    try:
        if arguments.web_command == "prepare-demo":
            from booster_web.demo import prepare_demo

            result = prepare_demo(
                arguments.project,
                demo_dir=arguments.demo_dir,
                timeout_seconds=arguments.timeout_seconds,
            )
            _print_json(result)
            return 0

        import uvicorn

        from booster_web.app import create_app

        application = create_app(
            project=arguments.project,
            mode=arguments.mode,
            demo_dir=arguments.demo_dir,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    uvicorn.run(application, host=arguments.host, port=arguments.port)
    return 0


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
    print(f"  Scan profile: {scan['profile']} ({'saved' if scan['saved'] else 'default'})")
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
    print(f"  Include dependencies: {'yes' if result['include_dependencies'] else 'no'}")


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
                _print_control_status(_control_status(root, "vscode", "workspace", None))
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
                    replace = input("Replace the existing entry? [y/N]: ").strip().lower()
                    if replace not in {"y", "yes"}:
                        print("Connection unchanged.")
                        continue
                    result = connect(client, scope, root, force=True)
                _print_connection_result(result, "connect")
            elif choice == "5":
                profile = input("Profile (quick, balanced, deep): ").strip().lower()
                if profile not in PROFILE_LIMITS:
                    print("Unknown profile. Settings unchanged.")
                    continue
                dependencies = input("Include dependency directories? [y/N]: ").strip().lower()
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
                scope = (
                    "user"
                    if client == "claude"
                    else input("Scope (workspace, user): ").strip().lower()
                )
                _print_connection_result(disconnect(client, scope, root), "disconnect")
            elif choice == "9":
                result = install_launcher()
                print(f"Launcher: {result['launcher_path']}")
                if not result.get("path_on_environment", False):
                    print(f"Add {result['user_bin']} to PATH, then open a new terminal.")
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
            definition = build_server_definition(arguments.client, arguments.project)
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
                    print(f"Add {result['user_bin']} to PATH, then open a new terminal.")
            return 0
    except ControlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"error: unknown control command: {command}", file=sys.stderr)
    return 2


def _home_config(arguments: argparse.Namespace):
    """Собирает HomeConfig с precedence CLI > explicit TOML > project > user."""
    from booster_home.config import load_home_config

    return load_home_config(
        project=arguments.project,
        config_path=arguments.home_config,
        cli_overrides={
            "base_url": arguments.base_url,
            "model": arguments.model,
            "api_key": arguments.api_key,
            "auth_token": arguments.auth_token,
            "listen": arguments.listen,
            "port": arguments.port,
            "context_window": arguments.context_window,
            "reserve_output": arguments.reserve_output,
            "workers": arguments.workers,
            "context_policy": arguments.context_policy,
            "verbose": arguments.verbose,
            "json_logs": arguments.json_logs,
            "no_persist": arguments.no_persist,
            "probe_generation": arguments.probe_generation,
        },
    )


def _home_status(config, as_json: bool) -> int:
    """Печатает только redacted status и безопасную reachability probe."""
    import httpx

    from booster_home.telemetry.logging import redact_endpoint

    auth_headers = (
        {"Authorization": f"Bearer {config.home.auth_token}"} if config.home.auth_token else {}
    )

    payload = {
        "command": "home status",
        "config": config.redacted(),
        "gateway": {
            "endpoint": f"http://{config.home.listen}:{config.home.port}",
            "reachable": False,
        },
    }
    try:
        response = httpx.get(
            f"http://{config.home.listen}:{config.home.port}/health",
            headers=auth_headers,
            timeout=0.25,
        )
        payload["gateway"]["reachable"] = response.is_success
        payload["gateway"]["health"] = (
            response.json() if response.is_success else {"status_code": response.status_code}
        )
    except httpx.HTTPError:
        payload["gateway"]["health"] = {"status": "unreachable"}
    if as_json:
        _print_json(payload)
    else:
        print("Booster Home status")
        print(f"  Gateway: {payload['gateway']['endpoint']}")
        print(f"  Reachable: {payload['gateway']['reachable']}")
        print(f"  Upstream: {redact_endpoint(config.upstream.base_url)}")
        print(f"  Model: {config.upstream.model}")
        print(f"  API key configured: {bool(config.upstream.api_key)}")
        print(f"  Context policy: {config.context.policy.value}")
    return 0


def _home_doctor(config, as_json: bool) -> int:
    """Проверяет конфигурацию, зависимости и возможность записи session store."""
    import importlib.util
    import tempfile

    import httpx

    checks: dict[str, object] = {
        "config": "ok",
        "fastapi": bool(importlib.util.find_spec("fastapi")),
        "httpx": bool(importlib.util.find_spec("httpx")),
        "uvicorn": bool(importlib.util.find_spec("uvicorn")),
        "pydantic": bool(importlib.util.find_spec("pydantic")),
        "project": str(config.project) if config.project else None,
        "project_exists": config.project.is_dir() if config.project else True,
        "api_key_configured": bool(config.upstream.api_key),
    }
    try:
        config.memory.root_dir or (
            (config.project or Path.cwd()) / ".agents" / "booster" / "runtime"
        )
        with tempfile.TemporaryDirectory(prefix="booster-home-doctor-") as path:
            probe = Path(path) / "write-test"
            probe.write_text("ok", encoding="utf-8")
            checks["session_store_write"] = probe.read_text(encoding="utf-8") == "ok"
    except OSError:
        checks["session_store_write"] = False
    if config.probe_generation:

        async def probe_generation() -> dict[str, object]:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        f"{config.upstream.base_url.rstrip('/')}/chat/completions",
                        headers=(
                            {"Authorization": f"Bearer {config.upstream.api_key}"}
                            if config.upstream.api_key
                            else {}
                        ),
                        json={
                            "model": config.upstream.model,
                            "messages": [{"role": "user", "content": "ping"}],
                            "max_tokens": 1,
                            "stream": False,
                        },
                    )
                return {"status_code": response.status_code, "ok": response.is_success}
            except httpx.HTTPError:
                return {"status": "unreachable", "ok": False}

        checks["generation_probe"] = asyncio.run(probe_generation())
    required_checks = (
        "config",
        "fastapi",
        "httpx",
        "uvicorn",
        "pydantic",
        "project_exists",
        "session_store_write",
    )
    checks["ok"] = all(checks.get(key) is not False for key in required_checks)
    if as_json:
        _print_json(checks)
    else:
        print("Booster Home doctor")
        for key, value in checks.items():
            print(f"  {key}: {value}")
    return 0 if checks["ok"] else 1


def _home_inspect_context(config, input_path: str | None, as_json: bool) -> int:
    """Выполняет compiler без network request и печатает explainability data."""
    from booster_home.context.budget import ContextBudgetManager
    from booster_home.context.compiler import ContextCompiler
    from booster_home.memory.artifact_store import ArtifactStore
    from booster_home.memory.pager import MemoryPager
    from booster_home.models import ChatCompletionRequest, ModelProfile, SessionContext

    raw = (
        json.loads(Path(input_path).read_text(encoding="utf-8"))
        if input_path
        else {"model": config.upstream.model, "messages": []}
    )
    request = ChatCompletionRequest.model_validate(raw)
    compiler = ContextCompiler(
        policy=config.context.policy,
        budget_manager=ContextBudgetManager(
            configured_context_window=config.context.context_window,
            reserve_output=config.context.reserve_output,
            safety_margin=config.context.safety_margin,
            soft_target_ratio=config.context.soft_target_ratio,
            hard_target_ratio=config.context.hard_target_ratio,
        ),
        pager=MemoryPager(
            ArtifactStore(
                config.memory.root_dir
                or ((config.project or Path.cwd()) / ".agents" / "booster" / "runtime"),
                config.memory.compression,
            ),
            enabled=config.effective_persistence and config.context.raw_artifacts,
        ),
    )
    compiled = asyncio.run(
        compiler.compile(
            request,
            SessionContext(session_id="inspect-context"),
            ModelProfile(id=request.model, context_window=None),
        )
    )
    payload = compiled.model_dump(mode="json")
    if as_json:
        _print_json(payload)
    else:
        print("Booster Home context inspection")
        print(f"  Original tokens: {compiled.original_tokens}")
        print(f"  Compiled tokens: {compiled.compiled_tokens}")
        print(f"  Removed tokens: {compiled.removed_tokens}")
        print(f"  Operations: {len(compiled.operations)}")
        print(f"  Artifacts: {len(compiled.artifact_refs)}")
    return 0


def _home(arguments: argparse.Namespace) -> int:
    config = _home_config(arguments)
    command = arguments.home_command
    if command == "status":
        return _home_status(config, arguments.json)
    if command == "doctor":
        return _home_doctor(config, arguments.json)
    if command == "inspect-context":
        return _home_inspect_context(config, arguments.input_path, arguments.json)
    if command == "sessions":
        from booster_home.memory.session_store import SessionStore

        deleted = asyncio.run(
            SessionStore(
                config.memory.root_dir
                or ((config.project or Path.cwd()) / ".agents" / "booster" / "runtime")
            ).delete(arguments.session_id)
        )
        payload = {"session_id": arguments.session_id, "deleted": deleted}
        if arguments.json:
            _print_json(payload)
        else:
            print("Session deleted" if deleted else "Session not found")
        return 0 if deleted else 1
    from booster_home.app import run_home

    run_home(config)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Запускает CLI Booster и возвращает код завершения для shell."""
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command in {"expand", "expance"}:
        return _expand(arguments)
    if arguments.command == "web":
        return _web(arguments)
    if arguments.command == "control":
        return _control(arguments)
    if arguments.command == "home":
        return _home(arguments)
    parser.error(f"Unknown command: {arguments.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
