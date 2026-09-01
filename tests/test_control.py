import json
import os
import sys
from pathlib import Path

import control
from cli import main as cli_main
from control import (
    LAUNCHER_MARKER,
    connect,
    disconnect,
    install_launcher,
    resolve_connection_target,
    scan_settings,
    update_scan_settings,
)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def test_connect_workspace_preserves_other_servers_and_creates_backup(tmp_path):
    config_path = tmp_path / ".vscode" / "mcp.json"
    original = {"servers": {"other": {"command": "other-mcp"}}, "inputs": []}
    write_json(config_path, original)

    result = connect("vscode", "workspace", tmp_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert result["updated"] is True
    assert config["servers"]["other"] == {"command": "other-mcp"}
    booster = config["servers"]["boosterLocal"]
    assert booster["type"] == "stdio"
    assert booster["env"]["REPOS"] == str(tmp_path)
    assert json.loads(Path(result["backup_path"]).read_text(encoding="utf-8")) == original

    second_result = connect("vscode", "workspace", tmp_path)
    assert second_result["updated"] is False
    assert second_result["reason"] == "already_configured"


def test_user_connection_is_portable_unless_repository_is_explicit(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()

    portable = connect("vscode", "user", project, home=home, platform_name="win32")
    target = resolve_connection_target("vscode", "user", project, home=home, platform_name="win32")
    servers = json.loads(target.config_path.read_text(encoding="utf-8"))["servers"]

    assert portable["repository_bound"] is False
    assert servers["Booster"]["env"] == {"CITY_PORT": "0"}
    assert servers["Booster"]["cwd"] != str(project)

    bound = connect(
        "vscode",
        "user",
        project,
        name="BoosterProject",
        bind_repository=True,
        home=home,
        platform_name="win32",
    )
    assert bound["repository_bound"] is True
    servers = json.loads(target.config_path.read_text(encoding="utf-8"))["servers"]
    assert servers["BoosterProject"]["env"]["REPOS"] == str(project)


def test_connect_and_disconnect_claude_user_config_on_macos_path(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()

    target = resolve_connection_target("claude", "user", project, home=home, platform_name="darwin")
    assert target.config_path == (
        home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    )

    connected = connect("claude", "user", project, home=home, platform_name="darwin")
    config = json.loads(target.config_path.read_text(encoding="utf-8"))
    assert connected["updated"] is True
    assert "Booster" in config["mcpServers"]
    assert "type" not in config["mcpServers"]["Booster"]

    disconnected = disconnect("claude", "user", project, home=home, platform_name="darwin")
    assert disconnected["updated"] is True
    assert "Booster" not in json.loads(target.config_path.read_text(encoding="utf-8"))["mcpServers"]


def test_control_scan_settings_and_cli_connect_are_scoped_to_project(tmp_path, capsys):
    scan_result = update_scan_settings(
        tmp_path, profile="quick", max_files=17, include_dependencies=True
    )
    assert scan_result["limits"]["max_files"] == 17
    assert scan_settings(tmp_path)["saved"] is True

    exit_code = cli_main(
        [
            "control",
            "connect",
            "--client",
            "vscode",
            "--scope",
            "workspace",
            "--project",
            str(tmp_path),
            "--json",
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert result["config_path"] == str(tmp_path / ".vscode" / "mcp.json")
    assert result["definition"]["env"]["REPOS"] == str(tmp_path)


def test_cli_user_connection_does_not_bind_repository(tmp_path, capsys, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))

    exit_code = cli_main(
        [
            "control",
            "connect",
            "--client",
            "vscode",
            "--scope",
            "user",
            "--project",
            str(tmp_path),
            "--json",
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert result["repository_bound"] is False
    assert result["definition"]["env"] == {"CITY_PORT": "0"}


def test_launcher_is_generated_for_windows_and_unix_without_touching_path(tmp_path):
    unix = install_launcher(home=tmp_path / "unix-home", platform_name="linux")
    unix_path = Path(unix["launcher_path"])
    assert unix_path.name == "booster"
    assert LAUNCHER_MARKER in unix_path.read_text(encoding="utf-8")
    if os.name != "nt":
        assert unix_path.stat().st_mode & 0o111

    windows = install_launcher(home=tmp_path / "windows-home", platform_name="win32")
    windows_path = Path(windows["launcher_path"])
    assert windows_path.name == "booster.cmd"
    assert LAUNCHER_MARKER in windows_path.read_text(encoding="utf-8")


def test_runtime_info_prefers_project_virtualenv_over_system_python(monkeypatch):
    project_root = Path(control.__file__).resolve().parent
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    if not venv_python.is_file():
        return

    monkeypatch.setattr(sys, "executable", r"C:\Python312\python.exe")

    assert control.runtime_info()["python"] == str(venv_python.resolve())
