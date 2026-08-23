from pathlib import Path

from visualizer import CodeCityVisualizer


def test_code_city_layout_is_compact_and_html_autoframes(tmp_path: Path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    for index in range(9):
        (source_dir / f"module_{index}.py").write_text(
            "\n".join(
                f"def function_{line}(value):\n"
                "    if value:\n"
                "        return value\n"
                "    return None"
                for line in range(index + 1)
            ),
            encoding="utf-8",
        )

    visualizer = CodeCityVisualizer()
    city = visualizer.generate_city_layout(str(tmp_path))
    buildings = city["buildings"]

    assert len(buildings) == 9
    assert max(item["position"]["x"] for item in buildings) < 200
    assert min(item["position"]["x"] for item in buildings) > -200
    assert max(item["position"]["z"] for item in buildings) < 200
    assert min(item["position"]["z"] for item in buildings) > -200
    assert all("weight" in item["metrics"] for item in buildings)

    output_path = tmp_path / "code_city.html"
    visualizer.generate_html(city, str(output_path))
    html = output_path.read_text(encoding="utf-8")

    assert "const cityBounds" in html
    assert "const citySpan" in html
    assert "CanvasTexture" in html
