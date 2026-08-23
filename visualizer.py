"""
Code City 3D - Визуализация архитектуры проекта в виде 3D города.
Здания = файлы, высота = метрики, связи = зависимости.
"""

import json
import math
from collections import defaultdict
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
        parts = path.parts

        # Игнорируем корень репозитория
        if len(parts) <= 2:
            return "root"

        # Берём первые 2-3 уровня вложенности как район
        district_parts = []
        for part in parts[1:-1]:  # пропускаем корень и имя файла
            if part in self.IGNORED_DIRS:
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
            if any(part in self.IGNORED_DIRS for part in file.parts):
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

        # Связи из графа вызовов (межфайловые)
        # Это более сложная логика, упростим
        pass

    def generate_html(self, city_data: Dict, output_path: str = "code_city.html"):
        """Генерирует HTML файл с 3D визуализацией."""
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code City 3D - {Path(city_data.get("repo", "")).name}</title>
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
        <div class="stat"><span class="stat-label">Sector:</span><span class="stat-value" id="stat-repo">{Path(city_data.get("repo", "")).name}</span></div>
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
        const cityData = {json.dumps(city_data)};

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
            
            const edgeLines = new THREE.LineSegments(edges, edgeMat);
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
                scene.add(line);
                connectionLines.push(line);
            }}
        }});

        // Interaction
        const raycaster = new THREE.Raycaster();
        const mouse = new THREE.Vector2();
        let hoveredBuilding = null;

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
                    
                    hoveredBuilding.material.emissive.setHex(0x222233);
                    hoveredBuilding.userData.outline.material.opacity = 1.0;
                    hoveredBuilding.userData.outline.material.color.lerp(new THREE.Color(0xffffff), 0.5);
                    
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
            if (hoveredBuilding) {{
                hoveredBuilding.material.emissive.setHex(0x000000);
                const c = hoveredBuilding.userData.color;
                hoveredBuilding.userData.outline.material.color.setStyle(c);
                hoveredBuilding.userData.outline.material.opacity = 0.8;
                hoveredBuilding = null;
            }}
        }}

        window.addEventListener('pointermove', onPointerMove);

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
