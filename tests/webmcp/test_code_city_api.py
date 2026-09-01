from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from booster_web.app import create_app
from booster_web.facade import BoosterFacade
from booster_web.security import RepositoryAllowlist
from visualizer import CodeCityVisualizer


def test_generated_code_city_exposes_programmatic_selection_api(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("def focus_target():\n    return True\n", encoding="utf-8")
    visualizer = CodeCityVisualizer()
    city = visualizer.generate_city_layout(str(tmp_path))
    output = tmp_path / "code_city.html"

    visualizer.generate_html(city, str(output))
    html = output.read_text(encoding="utf-8")

    assert "window.BoosterCity" in html
    assert "getSelection" in html
    assert "selectFile" in html
    assert "focusFile" in html
    assert "clearSelection" in html
    assert "highlightFiles" in html
    assert "highlightConnections" in html
    assert "clearHighlights" in html
    assert "showImpact" in html
    assert "showDiagnostics" in html
    assert "showHistory" in html
    assert "showRelatedTests" in html
    assert "showSnapshotComparison" in html
    assert "showSnapshotDiff" in html
    assert "resetView" in html
    assert "snapshotTransition" in html
    assert "fitBuildings" in html
    assert "impactCallerBuildings" in html
    if shutil.which("node"):
        script = tmp_path / "city.js"
        script.write_text(
            html.split("    <script>\n", 1)[1].split("\n    </script>", 1)[0],
            encoding="utf-8",
        )
        result = subprocess.run(
            ["node", "--check", str(script)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr
    assert "Math.sin(animationTime" in html
    assert "setMode" in html
    assert "pointerdown" in html
    assert "booster-city-selection" in html


def test_generated_code_city_escapes_repository_display_values(tmp_path: Path) -> None:
    city = {
        "repo": "<img src=x onerror=alert(1)>",
        "buildings": [],
        "connections": [],
        "districts": {},
        "metrics": {
            "files": 0,
            "lines": 0,
            "functions": 0,
            "classes": 0,
            "complexity": 0,
            "bytes": 0,
        },
    }
    output = tmp_path / "code_city.html"

    CodeCityVisualizer().generate_html(city, str(output))
    html = output.read_text(encoding="utf-8")

    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "<title>Code City 3D - <img" not in html


class CityIndexer:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def index_health(self) -> dict[str, object]:
        return {"repository": str(self.root), "generation_id": "city-generation", "ready": True}

    def stats(self) -> dict[str, object]:
        return {"generation_id": "city-generation", "vectors_in_faiss": 1}


def test_city_endpoint_returns_normalized_city_data(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("def target():\n    return True\n", encoding="utf-8")
    city_file = tmp_path / ".agents" / "booster" / "city.json"
    city_file.parent.mkdir(parents=True)
    city_file.write_text(
        json.dumps(
            {
                "repo": str(tmp_path),
                "buildings": [
                    {
                        "file": str(source),
                        "position": {"x": 0, "y": 0, "z": 0},
                        "size": {"width": 8, "height": 10, "depth": 8},
                    }
                ],
                "connections": [],
                "districts": {"root": [{"file": str(source)}]},
                "metrics": {"files": 1},
            }
        ),
        encoding="utf-8",
    )
    facade = BoosterFacade(
        CityIndexer(tmp_path),
        RepositoryAllowlist({"demo": tmp_path}),
    )

    with TestClient(create_app(facade=facade)) as client:
        response = client.get("/api/v1/city", params={"repo_id": "demo"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["buildings"][0]["file"] == "module.py"
    assert payload["districts"]["root"][0]["file"] == "module.py"
    assert payload["connections"] == []
    assert payload["metrics"] == {"files": 1}
    assert "available" not in payload
