"""
Code City 3D - Визуализация архитектуры проекта в виде 3D города.
Здания = файлы, высота = метрики, связи = зависимости.
"""

import json
import math
from collections import defaultdict
from html import escape
from pathlib import Path
from typing import Any, Dict, List

from grep_ast import filename_to_lang
from tree_sitter_language_pack import get_parser


class CodeCityVisualizer:
    """Генерация 3D визуализации кода в виде города."""

    # Цвета для разных типов файлов/компонентов
    COLORS = {
        "python": "#3776AB",  # синий
        "javascript": "#F7DF1E",  # жёлтый
        "typescript": "#3178C6",  # синий
        "rust": "#DEA584",  # оранжевый
        "go": "#00ADD8",  # голубой
        "java": "#B07219",  # коричневый
        "cpp": "#00599C",  # синий
        "c": "#555555",  # серый
        "test": "#FF6B6B",  # красный
        "config": "#4ECDC4",  # бирюзовый
        "default": "#95A5A6",  # серый
    }

    # Игнорируемые директории
    IGNORED_DIRS = {
        ".git",
        "node_modules",
        "venv",
        ".venv",
        "env",
        ".env",
        "__pycache__",
        ".pytest_cache",
        ".tox",
        ".nox",
        ".mypy_cache",
        ".ruff_cache",
        ".idea",
        ".vscode",
        ".vs",
        "bin",
        "obj",
        "target",
        "build",
        "dist",
        ".cache",
        "logs",
        "tmp",
        "temp",
    }

    def __init__(self, indexer=None):
        self.indexer = indexer
        self.buildings = []
        self.connections = []
        self.districts = {}
        self.metrics = {}
        self._layout_root: Path | None = None

    def collect_file_metrics(self, file_path: str) -> Dict[str, Any]:
        """Собирает подробные метрики для файла."""
        path = Path(file_path)
        if not path.exists():
            return {}

        lang = filename_to_lang(str(path))
        if not lang:
            return {}

        try:
            parser = get_parser(lang)
        except Exception:
            return {}

        try:
            code_bytes = path.read_bytes()
            code = code_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return {}

        tree = parser.parse(code_bytes)
        root = tree.root_node

        metrics = {
            "file": str(path),
            "filename": path.name,
            "extension": path.suffix,
            "language": lang,
            "lines": code.count("\n") + 1,
            "bytes": len(code_bytes),
            "functions": 0,
            "classes": 0,
            "methods": 0,
            "imports": 0,
            "complexity": 0,  # цикломатическая сложность (упрощённо)
            "comments": 0,
            "blank_lines": 0,
        }

        # Подсчёт строк кода и комментариев
        lines = code.split("\n")
        for line in lines:
            stripped = line.strip()
            if not stripped:
                metrics["blank_lines"] += 1
            elif stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("/*"):
                metrics["comments"] += 1

        # AST парсинг для метрик
        self._parse_metrics(root, code_bytes, metrics)

        # Добавляем данные из indexer если доступен
        symbols_by_file: dict[str, list[dict[str, Any]]] = {}
        if self.indexer:
            symbols_snapshot = getattr(self.indexer, "symbols_snapshot", None)
            symbols_by_file = (
                symbols_snapshot() if callable(symbols_snapshot) else self.indexer.symbols
            )
        if str(path) in symbols_by_file:
            symbols = symbols_by_file[str(path)]
            metrics["functions"] = len([s for s in symbols if s.get("name", "")])
            metrics["classes"] = len([s for s in symbols if "class" in s.get("name", "").lower()])

        # Вычисляем "вес" файла для высоты здания
        metrics["weight"] = self._calculate_weight(metrics)

        return metrics

    def _parse_metrics(self, node, code_bytes, metrics, depth=0):
        """Парсит AST для сбора метрик."""
        if depth > 500:
            return

        node_type = node.type

        # Считаем функции, классы, методы
        if "function" in node_type and "definition" in node_type:
            metrics["functions"] += 1
        elif "class" in node_type and ("definition" in node_type or "declaration" in node_type):
            metrics["classes"] += 1
        elif "method" in node_type:
            metrics["methods"] += 1

        # Считаем импорты
        if "import" in node_type:
            metrics["imports"] += 1

        # Цикломатическая сложность (упрощённо)
        if node_type in [
            "if_statement",
            "for_statement",
            "while_statement",
            "elif_clause",
            "if",
            "for",
            "while",
            "elif",
            "case",
            "catch",
            "except",
        ]:
            metrics["complexity"] += 1

        # Рекурсивный обход детей
        for child in node.children:
            self._parse_metrics(child, code_bytes, metrics, depth + 1)

    def _calculate_weight(self, metrics: Dict) -> float:
        """Вычисляет вес файла для определения высоты здания."""
        # Формула: строки + функции*10 + классы*15 + сложность*5
        return (
            metrics["lines"]
            + metrics["functions"] * 10
            + metrics["classes"] * 15
            + metrics["complexity"] * 5
        )

    def _get_district(self, file_path: str) -> str:
        """Определяет район (папку) для файла."""
        path = Path(file_path)
        relative = False
        if self._layout_root is not None:
            try:
                parts = path.resolve().relative_to(self._layout_root).parts
                relative = True
            except ValueError:
                parts = path.parts
        else:
            parts = path.parts

        # Игнорируем корень репозитория
        if len(parts) <= (1 if relative else 2):
            return "root"

        # Берём первые 2-3 уровня вложенности как район
        district_parts = []
        candidates = parts[:-1] if relative else parts[1:-1]
        for part in candidates:  # пропускаем корень и имя файла
            if part.casefold() in self.IGNORED_DIRS:
                continue
            district_parts.append(part)
            if len(district_parts) >= 2:
                break

        return "/".join(district_parts) if district_parts else "root"

    def _get_color(self, metrics: Dict) -> str:
        """Определяет цвет здания на основе типа файла."""
        filename = metrics.get("filename", "").lower()
        lang = metrics.get("language", "").lower()

        # Тесты
        if "test" in filename or filename.startswith("test_"):
            return self.COLORS["test"]

        # Конфиги
        if filename in [
            "package.json",
            "tsconfig.json",
            "settings.py",
            "config.py",
            "docker-compose.yml",
            ".env",
            "pyproject.toml",
        ]:
            return self.COLORS["config"]

        # По языку
        if lang in self.COLORS:
            return self.COLORS[lang]

        return self.COLORS["default"]

    def generate_city_layout(self, repo_path: str = None) -> Dict[str, Any]:
        """Генерирует 3D layout города."""
        if not repo_path:
            if self.indexer and self.indexer.repos:
                repo_path = self.indexer.repos[0]
            else:
                return {"error": "Нет репозиториев"}

        repo_path = Path(repo_path)
        if not repo_path.exists():
            return {"error": f"Репозиторий не найден: {repo_path}"}
        repo_path = repo_path.resolve()
        self._layout_root = repo_path

        self.buildings = []
        self.connections = []
        self.districts = defaultdict(list)
        total_metrics = {
            "files": 0,
            "lines": 0,
            "functions": 0,
            "classes": 0,
            "complexity": 0,
            "bytes": 0,
        }

        # Собираем все файлы
        files = []
        for file in repo_path.rglob("*"):
            if not file.is_file():
                continue
            try:
                relative_file = file.relative_to(repo_path)
            except ValueError:
                continue
            if any(part.casefold() in self.IGNORED_DIRS for part in relative_file.parts[:-1]):
                continue

            metrics = self.collect_file_metrics(str(file))
            if metrics and metrics.get("weight", 0) > 0:
                files.append(metrics)

                # Агрегируем метрики
                total_metrics["files"] += 1
                total_metrics["lines"] += metrics["lines"]
                total_metrics["functions"] += metrics["functions"]
                total_metrics["classes"] += metrics["classes"]
                total_metrics["complexity"] += metrics["complexity"]
                total_metrics["bytes"] += metrics["bytes"]

                # Распределяем по районам
                district = self._get_district(str(file))
                self.districts[district].append(metrics)

        # Вычисляем позиции зданий
        self._layout_buildings(files)

        # Генерируем связи (импорты/вызовы между файлами)
        self._generate_connections(repo_path)

        self.metrics = total_metrics

        return {
            "buildings": self.buildings,
            "connections": self.connections,
            "districts": dict(self.districts),
            "metrics": total_metrics,
            "repo": str(repo_path),
        }

    def _layout_buildings(self, files: List[Dict]):
        """Расставляет здания на плоскости."""
        district_files = defaultdict(list)
        for f in files:
            district = self._get_district(f["file"])
            district_files[district].append(f)

        # Pack districts into a square grid. A single horizontal strip makes
        # large repositories impossible to frame in the orthographic camera.
        building_id = 0
        districts = sorted(district_files.items())
        district_columns = max(1, math.ceil(math.sqrt(len(districts))))
        district_cell = 240
        district_rows = max(1, math.ceil(len(districts) / district_columns))
        city_width = district_columns * district_cell
        city_depth = district_rows * district_cell

        for district_index, (district, d_files) in enumerate(districts):
            d_files.sort(key=lambda x: x["weight"], reverse=True)
            local_columns = max(3, math.ceil(math.sqrt(len(d_files))))
            local_rows = max(1, math.ceil(len(d_files) / local_columns))
            local_spacing = 44
            district_x = (district_index % district_columns) * district_cell
            district_z = (district_index // district_columns) * district_cell
            local_offset_x = (local_columns - 1) * local_spacing / 2
            local_offset_z = (local_rows - 1) * local_spacing / 2

            for file_index, f in enumerate(d_files):
                base_width = min(30, max(8, math.log1p(f["weight"]) * 2.8))
                base_depth = min(30, max(8, math.log1p(f["weight"]) * 2.0))
                height = min(200, max(10, math.sqrt(f["weight"]) * 5.2))
                local_column = file_index % local_columns
                local_row = file_index // local_columns
                pos_x = district_x + local_column * local_spacing - local_offset_x
                pos_z = district_z + local_row * local_spacing - local_offset_z
                pos_y = 0

                building = {
                    "id": building_id,
                    "file": f["file"],
                    "filename": f["filename"],
                    "district": district,
                    "position": {"x": pos_x, "y": pos_y, "z": pos_z},
                    "size": {"width": base_width, "height": height, "depth": base_depth},
                    "color": self._get_color(f),
                    "metrics": {
                        "lines": f["lines"],
                        "functions": f["functions"],
                        "classes": f["classes"],
                        "complexity": f["complexity"],
                        "imports": f["imports"],
                        "bytes": f["bytes"],
                        "weight": f["weight"],
                    },
                }

                self.buildings.append(building)
                building_id += 1

        # Center the whole city around the origin so the default camera frames
        # both small repositories and large monorepos consistently.
        offset_x = city_width / 2 - district_cell / 2
        offset_z = city_depth / 2 - district_cell / 2
        for building in self.buildings:
            building["position"]["x"] -= offset_x
            building["position"]["z"] -= offset_z

    def _generate_connections(self, repo_path: Path):
        """Генерирует связи между зданиями на основе импортов/вызовов."""
        if not self.indexer:
            return

        # Строим маппинг файлов для быстрого поиска
        file_to_building = {}
        for b in self.buildings:
            file_to_building[b["file"]] = b["id"]

        # Связи из графа импортов
        graph_snapshot = getattr(self.indexer.graphs, "snapshot", None)
        import_graph = (
            graph_snapshot()["import_graph"]
            if callable(graph_snapshot)
            else self.indexer.graphs.import_graph
        )
        for file, imports in import_graph.items():
            if file not in file_to_building:
                continue

            source_id = file_to_building[file]

            # Пытаемся найти целевые файлы по именам импортов
            for imp in imports:
                # Упрощённый поиск: ищем файл с похожим именем
                for target_file, target_id in file_to_building.items():
                    target_name = Path(target_file).stem
                    if target_name in imp or imp.endswith(target_name):
                        if source_id != target_id:
                            self.connections.append(
                                {"source": source_id, "target": target_id, "type": "import"}
                            )
                        break

        # Связи из существующего индекса вызовов между известными символами.
        symbol_to_files = defaultdict(set)
        symbols_snapshot = getattr(self.indexer, "symbols_snapshot", None)
        symbols = symbols_snapshot() if callable(symbols_snapshot) else self.indexer.symbols
        if isinstance(symbols, dict):
            for file, records in symbols.items():
                if not isinstance(records, list):
                    continue
                for record in records:
                    if isinstance(record, dict) and isinstance(record.get("name"), str):
                        symbol_to_files[record["name"]].add(file)

        file_calls = getattr(self.indexer.graphs, "file_calls", {})
        for caller_file, pairs in file_calls.items():
            source_id = file_to_building.get(caller_file)
            if source_id is None or not isinstance(pairs, list):
                continue
            for pair in pairs:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    continue
                target_files = sorted(symbol_to_files.get(pair[1], set()))
                if not target_files:
                    continue
                target_id = file_to_building.get(target_files[0])
                if target_id is not None and source_id != target_id:
                    self.connections.append(
                        {"source": source_id, "target": target_id, "type": "call"}
                    )

    def generate_html(self, city_data: Dict, output_path: str = "code_city.html"):
        """Генерирует HTML файл с 3D визуализацией."""
        repo_name = escape(Path(city_data.get("repo", "")).name, quote=True)
        city_json = json.dumps(city_data).replace("</", "<\\/")
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code City 3D - {repo_name}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Consolas', 'Courier New', monospace;
            overflow: hidden;
            background: #050510;
            color: #00ffcc;
        }}
        #canvas {{
            width: 100vw;
            height: 100vh;
        }}
        /* Cyberpunk UI panels */
        .glass-panel {{
            position: absolute;
            background: rgba(5, 5, 16, 0.7);
            padding: 20px;
            border-radius: 8px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(0, 255, 204, 0.3);
            box-shadow: 0 0 15px rgba(0, 255, 204, 0.1), inset 0 0 20px rgba(0, 255, 204, 0.05);
            pointer-events: auto;
        }}
        #info-panel {{
            top: 20px;
            left: 20px;
            max-width: 350px;
            z-index: 10;
        }}
        #info-panel h2 {{
            font-size: 16px;
            margin-bottom: 15px;
            color: #fff;
            text-transform: uppercase;
            letter-spacing: 2px;
            border-bottom: 1px solid rgba(0, 255, 204, 0.5);
            padding-bottom: 5px;
        }}
        .stat {{
            display: flex;
            justify-content: space-between;
            padding: 6px 0;
            font-size: 14px;
        }}
        .stat-label {{
            color: #88aaff;
        }}
        .stat-value {{
            font-weight: bold;
            color: #00ffcc;
            text-shadow: 0 0 5px rgba(0, 255, 204, 0.5);
        }}
        #building-info {{
            bottom: 20px;
            left: 20px;
            min-width: 320px;
            display: none;
            z-index: 10;
        }}
        #building-info h3 {{
            font-size: 15px;
            margin-bottom: 12px;
            color: #fff;
            word-break: break-all;
            border-bottom: 1px solid #ff007f;
            padding-bottom: 5px;
            text-shadow: 0 0 5px rgba(255, 0, 127, 0.5);
        }}
        .metric {{
            display: flex;
            justify-content: space-between;
            padding: 4px 0;
            font-size: 13px;
        }}
        .metric-label {{ color: #88aaff; }}
        .metric-value {{ color: #ff007f; font-weight: bold; text-shadow: 0 0 5px rgba(255, 0, 127, 0.5); }}
        
        #controls {{
            top: 20px;
            right: 20px;
            min-width: 250px;
            z-index: 10;
        }}
        #controls label {{
            display: block;
            color: #88aaff;
            margin-bottom: 5px;
            font-size: 12px;
            text-transform: uppercase;
        }}
        #controls select, #controls input[type="range"] {{
            width: 100%;
            padding: 6px;
            margin-bottom: 15px;
            border-radius: 4px;
            border: 1px solid rgba(0, 255, 204, 0.5);
            background: rgba(0, 0, 0, 0.5);
            color: #fff;
            outline: none;
            font-family: inherit;
        }}
        #controls select:focus {{
            box-shadow: 0 0 10px rgba(0, 255, 204, 0.5);
        }}
        
        #legend {{
            bottom: 20px;
            right: 20px;
            z-index: 10;
        }}
        #legend h4 {{
            color: #fff;
            margin-bottom: 10px;
            font-size: 14px;
            letter-spacing: 1px;
            text-transform: uppercase;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            margin-bottom: 6px;
            font-size: 12px;
            color: #ccc;
        }}
        .legend-color {{
            width: 14px;
            height: 14px;
            margin-right: 10px;
            box-shadow: 0 0 8px currentColor;
        }}
        
        #loading {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(5, 5, 16, 0.9);
            color: #00ffcc;
            padding: 30px 50px;
            border-radius: 8px;
            font-size: 20px;
            text-transform: uppercase;
            letter-spacing: 3px;
            border: 1px solid #00ffcc;
            box-shadow: 0 0 20px rgba(0, 255, 204, 0.4);
            z-index: 1000;
        }}
        .hidden {{ display: none !important; }}
    </style>
</head>
<body>
    <div id="loading">Initialising Neural City...</div>
    <canvas id="canvas"></canvas>

    <div id="info-panel" class="glass-panel">
        <h2>System Status</h2>
        <div class="stat"><span class="stat-label">Sector:</span><span class="stat-value" id="stat-repo">{repo_name}</span></div>
        <div class="stat"><span class="stat-label">Nodes:</span><span class="stat-value" id="stat-files">{city_data.get("metrics", {}).get("files", 0)}</span></div>
        <div class="stat"><span class="stat-label">Lines:</span><span class="stat-value" id="stat-lines">{city_data.get("metrics", {}).get("lines", 0):,}</span></div>
        <div class="stat"><span class="stat-label">Functions:</span><span class="stat-value" id="stat-functions">{city_data.get("metrics", {}).get("functions", 0)}</span></div>
        <div class="stat"><span class="stat-label">Classes:</span><span class="stat-value" id="stat-classes">{city_data.get("metrics", {}).get("classes", 0)}</span></div>
        <div class="stat"><span class="stat-label">Complexity:</span><span class="stat-value" id="stat-complexity">{city_data.get("metrics", {}).get("complexity", 0)}</span></div>
        <div class="stat"><span class="stat-label">Payload:</span><span class="stat-value" id="stat-bytes">{city_data.get("metrics", {}).get("bytes", 0) / 1024:.1f} KB</span></div>
    </div>

    <div id="building-info" class="glass-panel">
        <h3 id="bi-filename">node_data</h3>
        <div class="metric"><span class="metric-label">Zone:</span><span class="metric-value" id="bi-district">root</span></div>
        <div class="metric"><span class="metric-label">Lines:</span><span class="metric-value" id="bi-lines">0</span></div>
        <div class="metric"><span class="metric-label">Funcs:</span><span class="metric-value" id="bi-functions">0</span></div>
        <div class="metric"><span class="metric-label">Classes:</span><span class="metric-value" id="bi-classes">0</span></div>
        <div class="metric"><span class="metric-label">Cyclomatic:</span><span class="metric-value" id="bi-complexity">0</span></div>
        <div class="metric"><span class="metric-label">Links:</span><span class="metric-value" id="bi-imports">0</span></div>
        <div class="metric"><span class="metric-label">Size:</span><span class="metric-value" id="bi-bytes">0 KB</span></div>
    </div>

    <div id="controls" class="glass-panel">
        <label>Vertical Scaling</label>
        <select id="height-metric">
            <option value="weight">Algorithm (Composite)</option>
            <option value="lines">Lines of Code</option>
            <option value="functions">Function Count</option>
            <option value="classes">Class Count</option>
            <option value="complexity">Cyclomatic Complexity</option>
        </select>
        
        <label>Data Streams</label>
        <label style="display:flex; align-items:center;">
            <input type="checkbox" id="show-connections" checked style="width:auto; margin:0 10px 0 0;"> Active Connections
        </label>
    </div>

    <div id="legend" class="glass-panel">
        <h4>Color Matrix</h4>
        <div class="legend-item"><div class="legend-color" style="background: #3776AB; color: #3776AB;"></div><span>Python</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #F7DF1E; color: #F7DF1E;"></div><span>JavaScript</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #3178C6; color: #3178C6;"></div><span>TypeScript</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #FF6B6B; color: #FF6B6B;"></div><span>Tests</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #4ECDC4; color: #4ECDC4;"></div><span>Config</span></div>
    </div>

    <!-- Three.js + PostProcessing -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/EffectComposer.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/RenderPass.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/ShaderPass.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/shaders/CopyShader.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/shaders/LuminosityHighPassShader.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/UnrealBloomPass.js"></script>

    <script>
        const cityData = {city_json};

        // Scene setup
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x050510);
        scene.fog = new THREE.FogExp2(0x050510, 0.0012);

        // Frame the generated city instead of assuming a fixed world size.
        const cityBounds = cityData.buildings.reduce((bounds, b) => {{
            bounds.minX = Math.min(bounds.minX, b.position.x - b.size.width / 2);
            bounds.maxX = Math.max(bounds.maxX, b.position.x + b.size.width / 2);
            bounds.minZ = Math.min(bounds.minZ, b.position.z - b.size.depth / 2);
            bounds.maxZ = Math.max(bounds.maxZ, b.position.z + b.size.depth / 2);
            return bounds;
        }}, {{ minX: Infinity, maxX: -Infinity, minZ: Infinity, maxZ: -Infinity }});
        const measuredWidth = Number.isFinite(cityBounds.minX) && Number.isFinite(cityBounds.maxX)
            ? cityBounds.maxX - cityBounds.minX
            : 0;
        const measuredDepth = Number.isFinite(cityBounds.minZ) && Number.isFinite(cityBounds.maxZ)
            ? cityBounds.maxZ - cityBounds.minZ
            : 0;
        const cityCenterX = measuredWidth ? (cityBounds.minX + cityBounds.maxX) / 2 : 0;
        const cityCenterZ = measuredDepth ? (cityBounds.minZ + cityBounds.maxZ) / 2 : 0;
        const citySpan = Math.max(
            measuredWidth,
            measuredDepth,
            420
        );
        const initialAspect = window.innerWidth / window.innerHeight;
        let viewSize = Math.max(300, citySpan * 0.95 / Math.min(1, initialAspect));
        const camera = new THREE.OrthographicCamera(
            -viewSize * initialAspect, viewSize * initialAspect,
            viewSize, -viewSize, 1, 5000
        );
        camera.position.set(cityCenterX + viewSize, viewSize * 0.85, cityCenterZ + viewSize);
        camera.lookAt(cityCenterX, 0, cityCenterZ);

        const renderer = new THREE.WebGLRenderer({{ canvas: document.getElementById('canvas'), antialias: false, powerPreference: "high-performance" }});
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.setPixelRatio(window.devicePixelRatio);
        renderer.toneMapping = THREE.ReinhardToneMapping;
        renderer.outputEncoding = THREE.sRGBEncoding;

        // Bloom Composer
        const renderScene = new THREE.RenderPass(scene, camera);
        const bloomPass = new THREE.UnrealBloomPass(new THREE.Vector2(window.innerWidth, window.innerHeight), 1.5, 0.4, 0.85);
        bloomPass.threshold = 0.05;
        bloomPass.strength = 1.0; 
        bloomPass.radius = 0.8;
        
        const composer = new THREE.EffectComposer(renderer);
        composer.addPass(renderScene);
        composer.addPass(bloomPass);

        // Controls
        const controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;
        controls.maxPolarAngle = Math.PI / 2 - 0.1;
        controls.target.set(cityCenterX, 0, cityCenterZ);
        controls.update();
        const initialCameraPosition = camera.position.clone();
        const initialCameraTarget = controls.target.clone();
        const initialViewSize = viewSize;

        // Lights
        const ambientLight = new THREE.AmbientLight(0x111122, 2.0);
        scene.add(ambientLight);
        
        // Cyber Grid Floor
        const floorSize = Math.max(3000, citySpan * 3);
        const gridHelper = new THREE.GridHelper(
            floorSize,
            Math.min(180, Math.max(60, Math.round(floorSize / 15))),
            0x00ffcc,
            0x002244
        );
        gridHelper.position.y = 0.1;
        gridHelper.material.opacity = 0.4;
        gridHelper.material.transparent = true;
        scene.add(gridHelper);

        const groundGeo = new THREE.PlaneGeometry(floorSize, floorSize);
        const groundMat = new THREE.MeshBasicMaterial({{ color: 0x020205 }});
        const ground = new THREE.Mesh(groundGeo, groundMat);
        ground.rotation.x = -Math.PI / 2;
        scene.add(ground);

        // Buildings
        const buildings = [];
        const buildingMeshes = [];
        const edgesMaterials = new Map();

        cityData.buildings.forEach((b, index) => {{
            const geometry = new THREE.BoxGeometry(b.size.width, b.size.height, b.size.depth);
            
            // Dark base material
            const material = new THREE.MeshLambertMaterial({{
                color: 0x0f0f1a,
                transparent: true,
                opacity: 0.9,
                emissive: new THREE.Color(b.color),
                emissiveIntensity: 0.08
            }});
            
            const building = new THREE.Mesh(geometry, material);
            building.position.set(b.position.x, b.size.height / 2, b.position.z);
            building.userData = {{ ...b, index, originalHeight: b.size.height, outline: null }};
            
            // Neon Edges
            const edges = new THREE.EdgesGeometry(geometry);
            let edgeMat = edgesMaterials.get(b.color);
            if (!edgeMat) {{
                edgeMat = new THREE.LineBasicMaterial({{ 
                    color: new THREE.Color(b.color), 
                    linewidth: 1, 
                    transparent: true, 
                    opacity: 0.8 
                }});
                edgesMaterials.set(b.color, edgeMat);
            }}
            
            const edgeLines = new THREE.LineSegments(edges, edgeMat.clone());
            building.add(edgeLines);
            building.userData.outline = edgeLines;

            // Keep filenames visible in the city without requiring a font asset.
            const labelCanvas = document.createElement('canvas');
            labelCanvas.width = 320;
            labelCanvas.height = 64;
            const labelContext = labelCanvas.getContext('2d');
            labelContext.font = 'bold 22px Consolas, monospace';
            labelContext.fillStyle = b.color;
            labelContext.shadowColor = b.color;
            labelContext.shadowBlur = 10;
            labelContext.fillText(b.filename.slice(0, 26), 8, 40);
            const labelTexture = new THREE.CanvasTexture(labelCanvas);
            const label = new THREE.Sprite(new THREE.SpriteMaterial({{
                map: labelTexture,
                transparent: true,
                depthTest: true
            }}));
            label.scale.set(Math.max(24, b.size.width * 2.8), 8, 1);
            label.position.set(0, b.size.height / 2 + 7, 0);
            building.add(label);

            scene.add(building);
            buildings.push(building);
            buildingMeshes.push(building);
        }});

        // Data connections (splines)
        const connectionLines = [];
        cityData.connections.forEach(conn => {{
            const source = buildings.find(b => b.userData.id === conn.source);
            const target = buildings.find(b => b.userData.id === conn.target);
            if (source && target) {{
                const p1 = source.position.clone();
                const p3 = target.position.clone();
                const distance = p1.distanceTo(p3);
                
                const p2 = p1.clone().lerp(p3, 0.5);
                p2.y += distance * 0.4;
                
                const curve = new THREE.QuadraticBezierCurve3(p1, p2, p3);
                const points = curve.getPoints(20);
                const geometry = new THREE.BufferGeometry().setFromPoints(points);
                
                const material = new THREE.LineBasicMaterial({{ 
                    color: 0x00ffcc, 
                    transparent: true, 
                    opacity: 0.3
                }});
                const line = new THREE.Line(geometry, material);
                line.userData = {{
                    ...conn,
                    sourceFile: source.userData.file,
                    targetFile: target.userData.file,
                    phase: connectionLines.length,
                    highlighted: false,
                    baseOpacity: 0.3
                }};
                scene.add(line);
                connectionLines.push(line);
            }}
        }});

        // Interaction
        const raycaster = new THREE.Raycaster();
        const mouse = new THREE.Vector2();
        let hoveredBuilding = null;
        let selectedBuilding = null;
        let highlightedBuildings = new Set();
        let impactBuildings = new Set();
        let impactPrimaryBuildings = new Set();
        let impactCallerBuildings = new Set();
        let impactCalleeBuildings = new Set();
        let impactTestBuildings = new Set();
        let impactSecondaryBuildings = new Set();
        let diagnosticBuildings = new Set();
        let snapshotAddedBuildings = new Set();
        let snapshotChangedBuildings = new Set();
        let snapshotStableBuildings = new Set();
        let snapshotGhosts = [];
        let cityMode = 'default';
        let cameraAnimation = null;
        let snapshotTransition = null;

        function normalizedCityPath(value) {{
            return String(value || '').replace(/\\\\/g, '/').replace(/^\\.\\//, '');
        }}

        function matchesBuildingPath(building, path) {{
            return pathsMatch(building.userData.file, path);
        }}

        function pathsMatch(left, right) {{
            const leftPath = normalizedCityPath(left);
            const rightPath = normalizedCityPath(right);
            return leftPath === rightPath ||
                leftPath.endsWith('/' + rightPath) ||
                rightPath.endsWith('/' + leftPath);
        }}

        function updateBuildingVisual(building) {{
            if (!building) return;
            const outline = building.userData.outline;
            if (building === selectedBuilding) {{
                building.material.opacity = 1.0;
                building.material.emissive.setHex(0x661144);
                building.material.emissiveIntensity = 0.35;
                outline.material.color.setStyle('#ff007f');
                outline.material.opacity = 1.0;
                return;
            }}
            if (snapshotAddedBuildings.has(building)) {{
                building.material.opacity = 0.95;
                building.material.emissive.setHex(0x164c32);
                building.material.emissiveIntensity = 0.3;
                outline.material.color.setStyle('#4dde8c');
                outline.material.opacity = 1.0;
                return;
            }}
            if (snapshotChangedBuildings.has(building)) {{
                building.material.opacity = 0.95;
                building.material.emissive.setHex(0x66501d);
                building.material.emissiveIntensity = 0.3;
                outline.material.color.setStyle('#f2bb65');
                outline.material.opacity = 1.0;
                return;
            }}
            if (snapshotStableBuildings.has(building)) {{
                building.material.opacity = 0.18;
                building.material.emissive.setHex(0x000000);
                building.material.emissiveIntensity = 0.05;
                outline.material.color.setStyle('#31505a');
                outline.material.opacity = 0.25;
                return;
            }}
            if (diagnosticBuildings.has(building)) {{
                building.material.opacity = 0.95;
                building.material.emissive.setHex(0x661f2b);
                building.material.emissiveIntensity = 0.3;
                outline.material.color.setStyle('#ef7180');
                outline.material.opacity = 1.0;
                return;
            }}
            if (impactPrimaryBuildings.has(building)) {{
                building.material.opacity = 1.0;
                building.material.emissive.setHex(0x661144);
                building.material.emissiveIntensity = 0.45;
                outline.material.color.setStyle('#ff007f');
                outline.material.opacity = 1.0;
                return;
            }}
            if (impactCallerBuildings.has(building)) {{
                building.material.opacity = 0.95;
                building.material.emissive.setHex(0x183b66);
                building.material.emissiveIntensity = 0.3;
                outline.material.color.setStyle('#6fa8ff');
                outline.material.opacity = 1.0;
                return;
            }}
            if (impactCalleeBuildings.has(building)) {{
                building.material.opacity = 0.95;
                building.material.emissive.setHex(0x422266);
                building.material.emissiveIntensity = 0.3;
                outline.material.color.setStyle('#b57cff');
                outline.material.opacity = 1.0;
                return;
            }}
            if (impactTestBuildings.has(building)) {{
                building.material.opacity = 0.95;
                building.material.emissive.setHex(0x164c32);
                building.material.emissiveIntensity = 0.3;
                outline.material.color.setStyle('#4dde8c');
                outline.material.opacity = 1.0;
                return;
            }}
            if (impactSecondaryBuildings.has(building)) {{
                building.material.opacity = 0.9;
                building.material.emissive.setHex(0x663311);
                building.material.emissiveIntensity = 0.3;
                outline.material.color.setStyle('#f2bb65');
                outline.material.opacity = 1.0;
                return;
            }}
            if (impactBuildings.size > 0) {{
                building.material.opacity = 0.16;
                building.material.emissive.setHex(0x000000);
                building.material.emissiveIntensity = 0.02;
                outline.material.color.setStyle('#284047');
                outline.material.opacity = 0.12;
                return;
            }}
            if (highlightedBuildings.has(building)) {{
                building.material.opacity = 0.95;
                building.material.emissive.setHex(0x114c4c);
                building.material.emissiveIntensity = 0.25;
                outline.material.color.setStyle('#38d4bd');
                outline.material.opacity = 1.0;
                return;
            }}
            if (building === hoveredBuilding) {{
                building.material.opacity = 0.95;
                building.material.emissive.setHex(0x222233);
                building.material.emissiveIntensity = 0.2;
                outline.material.color.lerp(new THREE.Color(0xffffff), 0.5);
                outline.material.opacity = 1.0;
                return;
            }}
            building.material.opacity = 0.9;
            building.material.emissive.setHex(0x000000);
            building.material.emissiveIntensity = 0.08;
            outline.material.color.setStyle(building.userData.color);
            outline.material.opacity = 0.8;
        }}

        function workspacePath(building) {{
            const repo = normalizedCityPath(cityData.repo);
            const file = normalizedCityPath(building.userData.file);
            return repo && file.startsWith(repo + '/') ? file.slice(repo.length + 1) : file;
        }}

        function setMode(mode) {{
            cityMode = String(mode || 'default');
            document.body.dataset.mode = cityMode;
            return true;
        }}

        function notifyParentSelection() {{
            if (window.parent === window) return;
            window.parent.postMessage({{
                type: 'booster-city-selection',
                path: selectedBuilding ? workspacePath(selectedBuilding) : null,
                symbol: null
            }}, window.location.origin);
        }}

        function setSelectedBuilding(building, notify = true) {{
            if (selectedBuilding === building) {{
                updateBuildingVisual(building);
                return;
            }}
            const previous = selectedBuilding;
            selectedBuilding = building;
            updateBuildingVisual(previous);
            updateBuildingVisual(selectedBuilding);
            if (selectedBuilding) showBuildingInfo(selectedBuilding.userData);
            else hideBuildingInfo();
            if (notify) notifyParentSelection();
        }}

        function getSelection() {{
            if (!selectedBuilding) return null;
            return {{
                file: selectedBuilding.userData.file,
                path: workspacePath(selectedBuilding),
                symbol: null
            }};
        }}

        function selectFile(path, notify = true) {{
            const building = buildings.find(item => matchesBuildingPath(item, path));
            if (!building) return false;
            setSelectedBuilding(building, notify);
            return true;
        }}

        function focusFile(path) {{
            const building = buildings.find(item => matchesBuildingPath(item, path));
            if (!building) return false;
            setSelectedBuilding(building, false);
            const target = building.position.clone();
            target.y = Math.max(0, building.userData.originalHeight * 0.35);
            const offset = camera.position.clone().sub(controls.target);
            const distance = Math.max(offset.length(), citySpan * 0.35, 120);
            const direction = offset.length() > 0
                ? offset.normalize()
                : new THREE.Vector3(1, 0.8, 1).normalize();
            cameraAnimation = {{
                fromPosition: camera.position.clone(),
                fromTarget: controls.target.clone(),
                toPosition: target.clone().add(direction.multiplyScalar(distance)),
                toTarget: target,
                startedAt: performance.now(),
                duration: 450
            }};
            return true;
        }}

        function fitBuildings(items) {{
            if (!items.length) return false;
            const bounds = items.reduce((value, building) => {{
                value.minX = Math.min(value.minX, building.position.x - building.userData.size.width / 2);
                value.maxX = Math.max(value.maxX, building.position.x + building.userData.size.width / 2);
                value.minZ = Math.min(value.minZ, building.position.z - building.userData.size.depth / 2);
                value.maxZ = Math.max(value.maxZ, building.position.z + building.userData.size.depth / 2);
                value.maxY = Math.max(value.maxY, building.userData.originalHeight);
                return value;
            }}, {{ minX: Infinity, maxX: -Infinity, minZ: Infinity, maxZ: -Infinity, maxY: 0 }});
            const center = new THREE.Vector3(
                (bounds.minX + bounds.maxX) / 2,
                Math.max(0, bounds.maxY * 0.35),
                (bounds.minZ + bounds.maxZ) / 2
            );
            const span = Math.max(bounds.maxX - bounds.minX, bounds.maxZ - bounds.minZ, 80);
            const aspect = window.innerWidth / window.innerHeight;
            viewSize = Math.max(180, span * 0.8 / Math.min(1, aspect));
            camera.left = -viewSize * aspect;
            camera.right = viewSize * aspect;
            camera.top = viewSize;
            camera.bottom = -viewSize;
            camera.updateProjectionMatrix();
            const offset = camera.position.clone().sub(controls.target);
            const distance = Math.max(offset.length(), citySpan * 0.2, 120);
            const direction = offset.length() > 0
                ? offset.normalize()
                : new THREE.Vector3(1, 0.8, 1).normalize();
            cameraAnimation = {{
                fromPosition: camera.position.clone(),
                fromTarget: controls.target.clone(),
                toPosition: center.clone().add(direction.multiplyScalar(distance)),
                toTarget: center,
                startedAt: performance.now(),
                duration: 450
            }};
            return true;
        }}

        function clearSelection() {{
            setSelectedBuilding(null);
            return true;
        }}

        function highlightFiles(paths) {{
            const requested = Array.isArray(paths) ? paths : [];
            impactBuildings.clear();
            impactPrimaryBuildings.clear();
            impactCallerBuildings.clear();
            impactCalleeBuildings.clear();
            impactTestBuildings.clear();
            impactSecondaryBuildings.clear();
            diagnosticBuildings.clear();
            snapshotAddedBuildings.clear();
            snapshotChangedBuildings.clear();
            snapshotStableBuildings.clear();
            snapshotTransition = null;
            highlightedBuildings = new Set(
                buildings.filter(building => requested.some(path => matchesBuildingPath(building, path)))
            );
            buildings.forEach(updateBuildingVisual);
            return highlightedBuildings.size;
        }}

        function highlightConnections(connections) {{
            const requested = Array.isArray(connections) ? connections : [];
            let count = 0;
            connectionLines.forEach(line => {{
                const active = requested.some(connection =>
                    (connection.source === line.userData.source &&
                        connection.target === line.userData.target) ||
                    (normalizedCityPath(line.userData.sourceFile).endsWith('/' + normalizedCityPath(connection.source)) &&
                        normalizedCityPath(line.userData.targetFile).endsWith('/' + normalizedCityPath(connection.target)))
                );
                line.userData.highlighted = active;
                line.material.opacity = active ? 0.95 : 0.12;
                if (active) count += 1;
            }});
            return count;
        }}

        function clearHighlights() {{
            highlightedBuildings.clear();
            impactBuildings.clear();
            impactPrimaryBuildings.clear();
            impactCallerBuildings.clear();
            impactCalleeBuildings.clear();
            impactTestBuildings.clear();
            impactSecondaryBuildings.clear();
            diagnosticBuildings.clear();
            snapshotAddedBuildings.clear();
            snapshotChangedBuildings.clear();
            snapshotStableBuildings.clear();
            snapshotGhosts.forEach(ghost => {{
                scene.remove(ghost);
                ghost.geometry.dispose();
                ghost.material.dispose();
            }});
            snapshotGhosts = [];
            snapshotTransition = null;
            connectionLines.forEach(line => {{
                line.userData.highlighted = false;
                line.material.opacity = line.userData.baseOpacity;
            }});
            buildings.forEach(updateBuildingVisual);
            return true;
        }}

        function showImpact(result) {{
            clearHighlights();
            const requested = Array.isArray(result?.affected_files) ? result.affected_files : [];
            const affectedBuildings = new Set(
                buildings.filter(building => requested.some(path => matchesBuildingPath(building, path)))
            );
            const targetPath = result?.target_file || null;
            impactPrimaryBuildings = new Set(
                buildings.filter(building => targetPath && matchesBuildingPath(building, targetPath))
            );
            const callerPaths = [];
            const calleePaths = [];
            (Array.isArray(result?.connections) ? result.connections : []).forEach(connection => {{
                if (targetPath && pathsMatch(connection.target, targetPath)) {{
                    callerPaths.push(connection.source);
                }}
                if (targetPath && pathsMatch(connection.source, targetPath)) {{
                    calleePaths.push(connection.target);
                }}
            }});
            impactCallerBuildings = new Set(
                buildings.filter(building => callerPaths.some(path => matchesBuildingPath(building, path)))
            );
            impactCalleeBuildings = new Set(
                buildings.filter(building => calleePaths.some(path => matchesBuildingPath(building, path)))
            );
            impactTestBuildings = new Set(
                buildings.filter(building =>
                    (Array.isArray(result?.tests) ? result.tests : [])
                        .some(path => matchesBuildingPath(building, path))
                )
            );
            impactBuildings = new Set([
                ...affectedBuildings,
                ...impactPrimaryBuildings,
                ...impactCallerBuildings,
                ...impactCalleeBuildings,
                ...impactTestBuildings,
            ]);
            impactSecondaryBuildings = new Set(
                [...impactBuildings].filter(building =>
                    !impactPrimaryBuildings.has(building) &&
                    !impactCallerBuildings.has(building) &&
                    !impactCalleeBuildings.has(building) &&
                    !impactTestBuildings.has(building)
                )
            );
            buildings.forEach(updateBuildingVisual);
            highlightConnections(result?.connections || []);
            if (targetPath) focusFile(targetPath);
            fitBuildings([...impactBuildings]);
            return impactBuildings.size;
        }}

        function showDiagnostics(result) {{
            clearHighlights();
            const findings = Array.isArray(result?.findings) ? result.findings : [];
            const requested = Array.isArray(result?.affected_files)
                ? result.affected_files
                : findings.map(finding => finding.file);
            diagnosticBuildings = new Set(
                buildings.filter(building => requested.some(path => matchesBuildingPath(building, path)))
            );
            buildings.forEach(updateBuildingVisual);
            return diagnosticBuildings.size;
        }}

        function showSnapshotComparison(result) {{
            clearHighlights();
            const added = Array.isArray(result?.added) ? result.added : [];
            const changed = Array.isArray(result?.changed) ? result.changed : [];
            const stable = Array.isArray(result?.stable) ? result.stable : [];
            const removed = Array.isArray(result?.removed) ? result.removed : [];
            snapshotAddedBuildings = new Set(
                buildings.filter(building => added.some(path => matchesBuildingPath(building, path)))
            );
            snapshotChangedBuildings = new Set(
                buildings.filter(building => changed.some(path => matchesBuildingPath(building, path)))
            );
            snapshotStableBuildings = new Set(
                buildings.filter(building => stable.some(path => matchesBuildingPath(building, path)))
            );
            buildings.forEach(updateBuildingVisual);
            removed.forEach((path, index) => {{
                const ghost = new THREE.Mesh(
                    new THREE.BoxGeometry(12, 8, 12),
                    new THREE.MeshBasicMaterial({{
                        color: 0xef7180,
                        transparent: true,
                        opacity: 0.24,
                        wireframe: true
                    }})
                );
                const column = index % 8;
                const row = Math.floor(index / 8);
                ghost.position.set(
                    cityCenterX - citySpan * 0.4 + column * 18,
                    4,
                    cityCenterZ - citySpan * 0.4 + row * 18
                );
                ghost.userData = {{ file: path, snapshotGhost: true }};
                scene.add(ghost);
                snapshotGhosts.push(ghost);
            }});
            snapshotTransition = {{ startedAt: performance.now(), duration: 500 }};
            return {{
                added: snapshotAddedBuildings.size,
                changed: snapshotChangedBuildings.size,
                stable: snapshotStableBuildings.size,
                removed: snapshotGhosts.length
            }};
        }}

        function showHistory(result) {{
            if (!result?.path) return false;
            clearHighlights();
            highlightFiles([result.path]);
            return focusFile(result.path);
        }}

        function showRelatedTests(paths, targetPath = null) {{
            clearHighlights();
            const requested = Array.isArray(paths) ? paths : [];
            impactTestBuildings = new Set(
                buildings.filter(building => requested.some(path => matchesBuildingPath(building, path)))
            );
            if (targetPath) {{
                impactPrimaryBuildings = new Set(
                    buildings.filter(building => matchesBuildingPath(building, targetPath))
                );
            }}
            impactBuildings = new Set([...impactPrimaryBuildings, ...impactTestBuildings]);
            buildings.forEach(updateBuildingVisual);
            if (targetPath) focusFile(targetPath);
            return impactTestBuildings.size;
        }}

        function resetView() {{
            clearHighlights();
            setSelectedBuilding(null);
            setMode('default');
            const aspect = window.innerWidth / window.innerHeight;
            viewSize = initialViewSize;
            camera.left = -viewSize * aspect;
            camera.right = viewSize * aspect;
            camera.top = viewSize;
            camera.bottom = -viewSize;
            camera.updateProjectionMatrix();
            cameraAnimation = {{
                fromPosition: camera.position.clone(),
                fromTarget: controls.target.clone(),
                toPosition: initialCameraPosition.clone(),
                toTarget: initialCameraTarget.clone(),
                startedAt: performance.now(),
                duration: 450
            }};
            return true;
        }}

        function onPointerMove(event) {{
            // Calculate mouse position in normalized device coordinates
            const rect = renderer.domElement.getBoundingClientRect();
            mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
            mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
            
            raycaster.setFromCamera(mouse, camera);
            const intersects = raycaster.intersectObjects(buildingMeshes);

            if (intersects.length > 0) {{
                const building = intersects[0].object;
                if (hoveredBuilding !== building) {{
                    resetHover();
                    hoveredBuilding = building;
                    document.body.style.cursor = 'pointer';
                    updateBuildingVisual(hoveredBuilding);
                    showBuildingInfo(hoveredBuilding.userData);
                }}
            }} else {{
                if (hoveredBuilding) {{
                    resetHover();
                    document.body.style.cursor = 'default';
                    hideBuildingInfo();
                }}
            }}
        }}

        function resetHover() {{
            const previous = hoveredBuilding;
            hoveredBuilding = null;
            updateBuildingVisual(previous);
        }}

        window.addEventListener('pointermove', onPointerMove);

        function onPointerDown(event) {{
            if (event.button !== 0) return;
            const rect = renderer.domElement.getBoundingClientRect();
            mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
            mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
            raycaster.setFromCamera(mouse, camera);
            const intersects = raycaster.intersectObjects(buildingMeshes);
            if (intersects.length > 0) selectFile(workspacePath(intersects[0].object));
            else setSelectedBuilding(null);
        }}

        renderer.domElement.addEventListener('pointerdown', onPointerDown);

        // UI Interactions
        function showBuildingInfo(data) {{
            const panel = document.getElementById('building-info');
            panel.style.display = 'block';
            document.getElementById('bi-filename').textContent = data.filename;
            document.getElementById('bi-district').textContent = data.district;
            document.getElementById('bi-lines').textContent = data.metrics.lines;
            document.getElementById('bi-functions').textContent = data.metrics.functions;
            document.getElementById('bi-classes').textContent = data.metrics.classes;
            document.getElementById('bi-complexity').textContent = data.metrics.complexity;
            document.getElementById('bi-imports').textContent = data.metrics.imports;
            document.getElementById('bi-bytes').textContent = (data.metrics.bytes / 1024).toFixed(1) + ' KB';
        }}

        function hideBuildingInfo() {{
            document.getElementById('building-info').style.display = 'none';
        }}

        window.BoosterCity = {{
            getSelection,
            setMode,
            selectFile,
            focusFile,
            clearSelection,
            highlightFiles,
            highlightConnections,
            clearHighlights,
            showImpact,
            showDiagnostics,
            showHistory,
            showRelatedTests,
            showSnapshotComparison,
            showSnapshotDiff: showSnapshotComparison,
            resetView
        }};

        document.getElementById('height-metric').addEventListener('change', (e) => {{
            const metric = e.target.value;
            buildings.forEach(b => {{
                const m = b.userData.metrics;
                let value;
                switch(metric) {{
                    case 'lines': value = m.lines; break;
                    case 'functions': value = m.functions * 10; break;
                    case 'classes': value = m.classes * 15; break;
                    case 'complexity': value = m.complexity * 5; break;
                    default: value = b.userData.metrics.weight || m.lines;
                }}
                const newHeight = Math.max(10, Math.min(200, value / 5));
                const scaleY = newHeight / b.userData.originalHeight;
                b.scale.y = scaleY;
                b.position.y = newHeight / 2;
            }});
        }});

        document.getElementById('show-connections').addEventListener('change', (e) => {{
            connectionLines.forEach(line => {{ line.visible = e.target.checked; }});
        }});

        // Resize
        window.addEventListener('resize', () => {{
            const aspect = window.innerWidth / window.innerHeight;
            viewSize = Math.max(300, citySpan * 0.95 / Math.min(1, aspect));
            camera.left = -viewSize * aspect;
            camera.right = viewSize * aspect;
            camera.top = viewSize;
            camera.bottom = -viewSize;
            camera.updateProjectionMatrix();
            camera.position.set(cityCenterX + viewSize, viewSize * 0.85, cityCenterZ + viewSize);
            camera.lookAt(cityCenterX, 0, cityCenterZ);
            renderer.setSize(window.innerWidth, window.innerHeight);
            composer.setSize(window.innerWidth, window.innerHeight);
        }});

        // Animation Loop
        function animate() {{
            requestAnimationFrame(animate);
            if (cameraAnimation) {{
                const elapsed = performance.now() - cameraAnimation.startedAt;
                const progress = Math.min(1, elapsed / cameraAnimation.duration);
                const eased = 1 - Math.pow(1 - progress, 3);
                camera.position.lerpVectors(
                    cameraAnimation.fromPosition,
                    cameraAnimation.toPosition,
                    eased
                );
                controls.target.lerpVectors(
                    cameraAnimation.fromTarget,
                    cameraAnimation.toTarget,
                    eased
                );
                if (progress >= 1) cameraAnimation = null;
            }}
            const animationTime = performance.now();
            connectionLines.forEach(line => {{
                const pulse = (Math.sin(animationTime * 0.004 + line.userData.phase) + 1) / 2;
                line.material.opacity = line.userData.highlighted
                    ? 0.65 + pulse * 0.3
                    : cityMode === 'architecture'
                        ? 0.18 + pulse * 0.1
                        : line.userData.baseOpacity;
            }});
            if (snapshotTransition) {{
                const progress = Math.min(
                    1,
                    (animationTime - snapshotTransition.startedAt) / snapshotTransition.duration
                );
                const eased = 1 - Math.pow(1 - progress, 3);
                buildings.forEach(building => building.scale.setScalar(0.85 + eased * 0.15));
                snapshotGhosts.forEach(ghost => ghost.material.opacity = eased * 0.24);
                if (progress >= 1) snapshotTransition = null;
            }}
            controls.update();
            composer.render();
        }}

        document.getElementById('loading').classList.add('hidden');
        animate();
    </script>
</body>
</html>"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        return output_path

    def generate_visualization(self, repo_path: str = None, output_path: str = "code_city.html"):
        """Полный цикл: генерация города + HTML."""
        city_data = self.generate_city_layout(repo_path)

        if "error" in city_data:
            return city_data

        html_path = self.generate_html(city_data, output_path)

        return {
            "success": True,
            "html_path": html_path,
            "metrics": city_data["metrics"],
            "buildings": len(city_data["buildings"]),
            "connections": len(city_data["connections"]),
            "districts": len(city_data["districts"]),
        }
