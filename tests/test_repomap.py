from __future__ import annotations

from pathlib import Path

from repomap import RepoMap
from repository_scanner import ScanConfig


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_architecture_map_keeps_modules_and_caps_giant_file(tmp_path: Path) -> None:
    _write(tmp_path / "package.json", '{"name":"monorepo"}\n')
    _write(tmp_path / "pyproject.toml", "[project]\nname='monorepo'\n")
    _write(
        tmp_path / "LEGION" / "QueryEngine.ts",
        "\n".join(f"export function legion_{i}() {{ return {i}; }}" for i in range(80)),
    )
    _write(tmp_path / "LEGION" / "bootstrap.ts", "export function bootstrap() { return true; }\n")
    _write(tmp_path / "frontend" / "app.ts", "export function renderApp() { return true; }\n")
    _write(tmp_path / "control-plane" / "routes.py", "def register_routes():\n    return True\n")
    _write(tmp_path / "contracts" / "schema.py", "class RequestSchema:\n    pass\n")

    repo_map = RepoMap(
        tmp_path,
        max_tokens=700,
        scan_config=ScanConfig.for_profile("deep"),
    )
    architecture = repo_map.get_architecture_map()
    coverage = repo_map.coverage_summary()

    assert "LEGION/QueryEngine.ts:" in architecture
    assert "frontend/app.ts:" in architecture
    assert "control-plane/routes.py:" in architecture
    assert "contracts/schema.py:" in architecture
    assert "package.json:" in architecture or "pyproject.toml:" in architecture
    assert set(coverage["represented_modules"]) >= {
        "LEGION",
        "frontend",
        "control-plane",
        "contracts",
    }
    assert architecture.count("def legion_") <= 20
    assert coverage["symbol_cap_per_file"] == 20
