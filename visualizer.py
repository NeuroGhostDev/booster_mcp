"""
Code City 3D - Визуализация архитектуры проекта в виде 3D города.
Здания = файлы, высота = метрики, связи = зависимости.
"""
import os
import json
import math
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional
from tree_sitter_language_pack import get_parser
from grep_ast import filename_to_lang


class CodeCityVisualizer:
    """Генерация 3D визуализации кода в виде города."""

    # Цвета для разных типов файлов/компонентов
    COLORS = {
        'python': '#3776AB',      # синий
        'javascript': '#F7DF1E',  # жёлтый
        'typescript': '#3178C6',  # синий
        'rust': '#DEA584',        # оранжевый
        'go': '#00ADD8',          # голубой
        'java': '#B07219',        # коричневый
        'cpp': '#00599C',         # синий
        'c': '#555555',           # серый
        'test': '#FF6B6B',        # красный
        'config': '#4ECDC4',      # бирюзовый
        'default': '#95A5A6',     # серый
    }

    # Игнорируемые директории
    IGNORED_DIRS = {
        ".git", "node_modules", "venv", ".venv", "env", ".env",
        "__pycache__", ".pytest_cache", ".tox", ".nox", ".mypy_cache",
        ".ruff_cache", ".idea", ".vscode", ".vs", "bin", "obj",
        "target", "build", "dist", ".cache", "logs", "tmp", "temp",
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
            'file': str(path),
            'filename': path.name,
            'extension': path.suffix,
            'language': lang,
            'lines': code.count('\n') + 1,
            'bytes': len(code_bytes),
            'functions': 0,
            'classes': 0,
            'methods': 0,
            'imports': 0,
            'complexity': 0,  # цикломатическая сложность (упрощённо)
            'comments': 0,
            'blank_lines': 0,
        }

        # Подсчёт строк кода и комментариев
        lines = code.split('\n')
        for line in lines:
            stripped = line.strip()
            if not stripped:
                metrics['blank_lines'] += 1
            elif stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('/*'):
                metrics['comments'] += 1

        # AST парсинг для метрик
        self._parse_metrics(root, code_bytes, metrics)

        # Добавляем данные из indexer если доступен
        if self.indexer and str(path) in self.indexer.symbols:
            symbols = self.indexer.symbols[str(path)]
            metrics['functions'] = len([s for s in symbols if s.get('name', '')])
            metrics['classes'] = len([s for s in symbols if 'class' in s.get('name', '').lower()])

        # Вычисляем "вес" файла для высоты здания
        metrics['weight'] = self._calculate_weight(metrics)

        return metrics

    def _parse_metrics(self, node, code_bytes, metrics, depth=0):
        """Парсит AST для сбора метрик."""
        if depth > 500:
            return

        node_type = node.type

        # Считаем функции, классы, методы
        if 'function' in node_type and 'definition' in node_type:
            metrics['functions'] += 1
        elif 'class' in node_type and ('definition' in node_type or 'declaration' in node_type):
            metrics['classes'] += 1
        elif 'method' in node_type:
            metrics['methods'] += 1

        # Считаем импорты
        if 'import' in node_type:
            metrics['imports'] += 1

        # Цикломатическая сложность (упрощённо)
        if node_type in ['if_statement', 'for_statement', 'while_statement', 'elif_clause',
                         'if', 'for', 'while', 'elif', 'case', 'catch', 'except']:
            metrics['complexity'] += 1

        # Рекурсивный обход детей
        for child in node.children:
            self._parse_metrics(child, code_bytes, metrics, depth + 1)

    def _calculate_weight(self, metrics: Dict) -> float:
        """Вычисляет вес файла для определения высоты здания."""
        # Формула: строки + функции*10 + классы*15 + сложность*5
        return (
            metrics['lines'] +
            metrics['functions'] * 10 +
            metrics['classes'] * 15 +
            metrics['complexity'] * 5
        )

    def _get_district(self, file_path: str) -> str:
        """Определяет район (папку) для файла."""
        path = Path(file_path)
        parts = path.parts

        # Игнорируем корень репозитория
        if len(parts) <= 2:
            return 'root'

        # Берём первые 2-3 уровня вложенности как район
        district_parts = []
        for part in parts[1:-1]:  # пропускаем корень и имя файла
            if part in self.IGNORED_DIRS:
                continue
            district_parts.append(part)
            if len(district_parts) >= 2:
                break

        return '/'.join(district_parts) if district_parts else 'root'

    def _get_color(self, metrics: Dict) -> str:
        """Определяет цвет здания на основе типа файла."""
        filename = metrics.get('filename', '').lower()
        lang = metrics.get('language', '').lower()

        # Тесты
        if 'test' in filename or filename.startswith('test_'):
            return self.COLORS['test']

        # Конфиги
        if filename in ['package.json', 'tsconfig.json', 'settings.py', 'config.py',
                        'docker-compose.yml', '.env', 'pyproject.toml']:
            return self.COLORS['config']

        # По языку
        if lang in self.COLORS:
            return self.COLORS[lang]

        return self.COLORS['default']

    def generate_city_layout(self, repo_path: str = None) -> Dict[str, Any]:
        """Генерирует 3D layout города."""
        if not repo_path:
            if self.indexer and self.indexer.repos:
                repo_path = self.indexer.repos[0]
            else:
                return {'error': 'Нет репозиториев'}

        repo_path = Path(repo_path)
        if not repo_path.exists():
            return {'error': f'Репозиторий не найден: {repo_path}'}

        self.buildings = []
        self.districts = defaultdict(list)
        total_metrics = {
            'files': 0,
            'lines': 0,
            'functions': 0,
            'classes': 0,
            'complexity': 0,
            'bytes': 0,
        }

        # Собираем все файлы
        files = []
        for file in repo_path.rglob("*"):
            if not file.is_file():
                continue
            if any(part in self.IGNORED_DIRS for part in file.parts):
                continue

            metrics = self.collect_file_metrics(str(file))
            if metrics and metrics.get('weight', 0) > 0:
                files.append(metrics)

                # Агрегируем метрики
                total_metrics['files'] += 1
                total_metrics['lines'] += metrics['lines']
                total_metrics['functions'] += metrics['functions']
                total_metrics['classes'] += metrics['classes']
                total_metrics['complexity'] += metrics['complexity']
                total_metrics['bytes'] += metrics['bytes']

                # Распределяем по районам
                district = self._get_district(str(file))
                self.districts[district].append(metrics)

        # Вычисляем позиции зданий
        self._layout_buildings(files)

        # Генерируем связи (импорты/вызовы между файлами)
        self._generate_connections(repo_path)

        self.metrics = total_metrics

        return {
            'buildings': self.buildings,
            'connections': self.connections,
            'districts': dict(self.districts),
            'metrics': total_metrics,
            'repo': str(repo_path),
        }

    def _layout_buildings(self, files: List[Dict]):
        """Расставляет здания на плоскости."""
        # Группируем по районам
        district_files = defaultdict(list)
        for f in files:
            district = self._get_district(f['file'])
            district_files[district].append(f)

        # Вычисляем позиции
        building_id = 0
        district_offset_x = 0
        district_spacing = 150  # расстояние между районами

        for district, d_files in sorted(district_files.items()):
            # Сортируем файлы по весу внутри района
            d_files.sort(key=lambda x: x['weight'], reverse=True)

            # Позиция в пределах района
            local_x = 0
            local_z = 0
            row_width = 0
            max_in_row = max(5, int(math.sqrt(len(d_files))))
            count_in_row = 0

            for f in d_files:
                # Размеры здания
                base_width = min(30, max(8, math.log(f['weight']) * 3))
                base_depth = min(30, max(8, math.log(f['weight']) * 2))
                height = min(200, max(10, f['weight'] / 5))

                # Позиция
                pos_x = district_offset_x + local_x
                pos_z = local_z
                pos_y = 0  # на земле

                building = {
                    'id': building_id,
                    'file': f['file'],
                    'filename': f['filename'],
                    'district': district,
                    'position': {'x': pos_x, 'y': pos_y, 'z': pos_z},
                    'size': {'width': base_width, 'height': height, 'depth': base_depth},
                    'color': self._get_color(f),
                    'metrics': {
                        'lines': f['lines'],
                        'functions': f['functions'],
                        'classes': f['classes'],
                        'complexity': f['complexity'],
                        'imports': f['imports'],
                        'bytes': f['bytes'],
                    }
                }

                self.buildings.append(building)
                building_id += 1

                # Смещение для следующего здания
                local_x += base_width + 5
                row_width = max(row_width, base_width + 5)
                count_in_row += 1

                if count_in_row >= max_in_row:
                    local_x = 0
                    local_z += base_depth + 10
                    count_in_row = 0

            # Смещение для следующего района
            district_offset_x += row_width + district_spacing

    def _generate_connections(self, repo_path: Path):
        """Генерирует связи между зданиями на основе импортов/вызовов."""
        if not self.indexer:
            return

        # Строим маппинг файлов для быстрого поиска
        file_to_building = {}
        for b in self.buildings:
            file_to_building[b['file']] = b['id']

        # Связи из графа импортов
        for file, imports in self.indexer.graphs.import_graph.items():
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
                            self.connections.append({
                                'source': source_id,
                                'target': target_id,
                                'type': 'import'
                            })
                        break

        # Связи из графа вызовов (межфайловые)
        # Это более сложная логика, упростим
        pass

    def generate_html(self, city_data: Dict, output_path: str = 'code_city.html'):
        """Генерирует HTML файл с 3D визуализацией."""
        html = f'''<!DOCTYPE html>
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
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            overflow: hidden;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        }}
        #canvas {{
            width: 100vw;
            height: 100vh;
        }}
        #info-panel {{
            position: absolute;
            top: 20px;
            left: 20px;
            background: rgba(0, 0, 0, 0.85);
            color: #fff;
            padding: 20px;
            border-radius: 12px;
            max-width: 350px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }}
        #info-panel h2 {{
            font-size: 18px;
            margin-bottom: 15px;
            color: #4ECDC4;
        }}
        #info-panel .stat {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        #info-panel .stat:last-child {{
            border-bottom: none;
        }}
        #info-panel .stat-label {{
            color: #aaa;
        }}
        #info-panel .stat-value {{
            font-weight: bold;
            color: #fff;
        }}
        #building-info {{
            position: absolute;
            bottom: 20px;
            left: 20px;
            background: rgba(0, 0, 0, 0.9);
            color: #fff;
            padding: 20px;
            border-radius: 12px;
            min-width: 300px;
            max-width: 450px;
            display: none;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.15);
            box-shadow: 0 8px 32px rgba(0,0,0,0.4);
        }}
        #building-info h3 {{
            font-size: 16px;
            margin-bottom: 12px;
            color: #3776AB;
            word-break: break-all;
        }}
        #building-info .metric {{
            display: flex;
            justify-content: space-between;
            padding: 6px 0;
            font-size: 14px;
        }}
        #building-info .metric-label {{
            color: #888;
        }}
        #building-info .metric-value {{
            font-weight: bold;
        }}
        #controls {{
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(0, 0, 0, 0.85);
            padding: 15px;
            border-radius: 12px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
        }}
        #controls label {{
            display: block;
            color: #aaa;
            margin-bottom: 8px;
            font-size: 13px;
        }}
        #controls select, #controls input {{
            width: 100%;
            padding: 8px;
            margin-bottom: 12px;
            border-radius: 6px;
            border: 1px solid #444;
            background: #222;
            color: #fff;
            cursor: pointer;
        }}
        #legend {{
            position: absolute;
            bottom: 20px;
            right: 20px;
            background: rgba(0, 0, 0, 0.85);
            padding: 15px;
            border-radius: 12px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
        }}
        #legend h4 {{
            color: #fff;
            margin-bottom: 10px;
            font-size: 14px;
        }}
        #legend .legend-item {{
            display: flex;
            align-items: center;
            margin-bottom: 8px;
            font-size: 12px;
            color: #ccc;
        }}
        #legend .legend-color {{
            width: 16px;
            height: 16px;
            border-radius: 3px;
            margin-right: 8px;
        }}
        #loading {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0, 0, 0, 0.9);
            color: #fff;
            padding: 30px 50px;
            border-radius: 12px;
            font-size: 18px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .hidden {{
            display: none !important;
        }}
    </style>
</head>
<body>
    <div id="loading">🏗️ Loading Code City...</div>
    <canvas id="canvas"></canvas>

    <div id="info-panel">
        <h2>📊 Project Statistics</h2>
        <div class="stat">
            <span class="stat-label">Repository:</span>
            <span class="stat-value" id="stat-repo">{Path(city_data.get("repo", "")).name}</span>
        </div>
        <div class="stat">
            <span class="stat-label">Total Files:</span>
            <span class="stat-value" id="stat-files">{city_data.get("metrics", {}).get("files", 0)}</span>
        </div>
        <div class="stat">
            <span class="stat-label">Lines of Code:</span>
            <span class="stat-value" id="stat-lines">{city_data.get("metrics", {}).get("lines", 0):,}</span>
        </div>
        <div class="stat">
            <span class="stat-label">Functions:</span>
            <span class="stat-value" id="stat-functions">{city_data.get("metrics", {}).get("functions", 0)}</span>
        </div>
        <div class="stat">
            <span class="stat-label">Classes:</span>
            <span class="stat-value" id="stat-classes">{city_data.get("metrics", {}).get("classes", 0)}</span>
        </div>
        <div class="stat">
            <span class="stat-label">Complexity:</span>
            <span class="stat-value" id="stat-complexity">{city_data.get("metrics", {}).get("complexity", 0)}</span>
        </div>
        <div class="stat">
            <span class="stat-label">Size:</span>
            <span class="stat-value" id="stat-bytes">{city_data.get("metrics", {}).get("bytes", 0) / 1024:.1f} KB</span>
        </div>
    </div>

    <div id="building-info">
        <h3 id="bi-filename">filename.py</h3>
        <div class="metric">
            <span class="metric-label">District:</span>
            <span class="metric-value" id="bi-district">root</span>
        </div>
        <div class="metric">
            <span class="metric-label">Lines:</span>
            <span class="metric-value" id="bi-lines">0</span>
        </div>
        <div class="metric">
            <span class="metric-label">Functions:</span>
            <span class="metric-value" id="bi-functions">0</span>
        </div>
        <div class="metric">
            <span class="metric-label">Classes:</span>
            <span class="metric-value" id="bi-classes">0</span>
        </div>
        <div class="metric">
            <span class="metric-label">Complexity:</span>
            <span class="metric-value" id="bi-complexity">0</span>
        </div>
        <div class="metric">
            <span class="metric-label">Imports:</span>
            <span class="metric-value" id="bi-imports">0</span>
        </div>
        <div class="metric">
            <span class="metric-label">Size:</span>
            <span class="metric-value" id="bi-bytes">0 KB</span>
        </div>
    </div>

    <div id="controls">
        <label for="height-metric">Height Metric:</label>
        <select id="height-metric">
            <option value="weight">Weight (composite)</option>
            <option value="lines">Lines of Code</option>
            <option value="functions">Functions</option>
            <option value="classes">Classes</option>
            <option value="complexity">Complexity</option>
        </select>

        <label for="color-metric">Color By:</label>
        <select id="color-metric">
            <option value="language">Language</option>
            <option value="district">District</option>
            <option value="complexity">Complexity</option>
        </select>

        <label for="show-connections">Show Connections:</label>
        <input type="checkbox" id="show-connections" checked>

        <label for="min-height">Min Building Height:</label>
        <input type="range" id="min-height" min="5" max="100" value="10">
    </div>

    <div id="legend">
        <h4>🎨 Legend</h4>
        <div class="legend-item">
            <div class="legend-color" style="background: #3776AB;"></div>
            <span>Python</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #F7DF1E;"></div>
            <span>JavaScript</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #3178C6;"></div>
            <span>TypeScript</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #FF6B6B;"></div>
            <span>Tests</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #4ECDC4;"></div>
            <span>Config</span>
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    <script>
        // City data from Python
        const cityData = {json.dumps(city_data)};

        // Three.js setup
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x1a1a2e);
        scene.fog = new THREE.Fog(0x1a1a2e, 500, 1500);

        const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 5000);
        camera.position.set(200, 300, 400);

        const renderer = new THREE.WebGLRenderer({{ canvas: document.getElementById('canvas'), antialias: true }});
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.shadowMap.enabled = true;

        const controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;
        controls.maxPolarAngle = Math.PI / 2 - 0.1;
        controls.minDistance = 50;
        controls.maxDistance = 1500;

        // Lighting
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
        scene.add(ambientLight);

        const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
        directionalLight.position.set(200, 500, 200);
        directionalLight.castShadow = true;
        scene.add(directionalLight);

        const hemisphereLight = new THREE.HemisphereLight(0x87ceeb, 0x545454, 0.4);
        scene.add(hemisphereLight);

        // Ground plane
        const groundGeometry = new THREE.PlaneGeometry(2000, 2000);
        const groundMaterial = new THREE.MeshStandardMaterial({{
            color: 0x2d3436,
            roughness: 0.8,
            metalness: 0.2
        }});
        const ground = new THREE.Mesh(groundGeometry, groundMaterial);
        ground.rotation.x = -Math.PI / 2;
        ground.receiveShadow = true;
        scene.add(ground);

        // Grid helper
        const gridHelper = new THREE.GridHelper(2000, 50, 0x444444, 0x222222);
        scene.add(gridHelper);

        // Buildings
        const buildings = [];
        const buildingMeshes = [];

        cityData.buildings.forEach((b, index) => {{
            const geometry = new THREE.BoxGeometry(b.size.width, b.size.height, b.size.depth);
            const material = new THREE.MeshStandardMaterial({{
                color: b.color,
                roughness: 0.3,
                metalness: 0.5,
                transparent: true,
                opacity: 0.9
            }});
            const building = new THREE.Mesh(geometry, material);
            building.position.set(
                b.position.x,
                b.size.height / 2,
                b.position.z
            );
            building.castShadow = true;
            building.receiveShadow = true;
            building.userData = {{ ...b, index }};

            scene.add(building);
            buildings.push(building);
            buildingMeshes.push(building);
        }});

        // Connections
        const connectionLines = [];
        cityData.connections.forEach(conn => {{
            const source = buildings.find(b => b.userData.id === conn.source);
            const target = buildings.find(b => b.userData.id === conn.target);
            if (source && target) {{
                const points = [];
                points.push(source.position);
                points.push(target.position);
                const geometry = new THREE.BufferGeometry().setFromPoints(points);
                const material = new THREE.LineBasicMaterial({{ color: 0x4ECDC4, transparent: true, opacity: 0.4 }});
                const line = new THREE.Line(geometry, material);
                scene.add(line);
                connectionLines.push(line);
            }}
        }});

        // Raycaster for interaction
        const raycaster = new THREE.Raycaster();
        const mouse = new THREE.Vector2();
        let hoveredBuilding = null;

        function onMouseMove(event) {{
            mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
            mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

            raycaster.setFromCamera(mouse, camera);
            const intersects = raycaster.intersectObjects(buildingMeshes);

            if (intersects.length > 0) {{
                const building = intersects[0].object;
                if (hoveredBuilding !== building) {{
                    hoveredBuilding = building;
                    document.body.style.cursor = 'pointer';

                    // Highlight
                    buildingMeshes.forEach(b => {{
                        b.material.emissive.setHex(0x000000);
                    }});
                    building.material.emissive.setHex(0x333333);

                    // Show info
                    showBuildingInfo(building.userData);
                }}
            }} else {{
                if (hoveredBuilding) {{
                    hoveredBuilding.material.emissive.setHex(0x000000);
                    hoveredBuilding = null;
                    document.body.style.cursor = 'default';
                    hideBuildingInfo();
                }}
            }}
        }}

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

        window.addEventListener('mousemove', onMouseMove);

        // Controls
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
                b.scale.y = newHeight / b.userData.size.height;
                b.position.y = (newHeight - b.userData.size.height) / 2;
            }});
        }});

        document.getElementById('show-connections').addEventListener('change', (e) => {{
            connectionLines.forEach(line => {{
                line.visible = e.target.checked;
            }});
        }});

        // Animation
        function animate() {{
            requestAnimationFrame(animate);
            controls.update();
            renderer.render(scene, camera);
        }}

        // Handle resize
        window.addEventListener('resize', () => {{
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }});

        // Hide loading
        document.getElementById('loading').classList.add('hidden');

        animate();
    </script>
</body>
</html>
'''
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        return output_path

    def generate_visualization(self, repo_path: str = None, output_path: str = 'code_city.html'):
        """Полный цикл: генерация города + HTML."""
        city_data = self.generate_city_layout(repo_path)

        if 'error' in city_data:
            return city_data

        html_path = self.generate_html(city_data, output_path)

        return {
            'success': True,
            'html_path': html_path,
            'metrics': city_data['metrics'],
            'buildings': len(city_data['buildings']),
            'connections': len(city_data['connections']),
            'districts': len(city_data['districts']),
        }
