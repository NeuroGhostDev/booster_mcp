"""
RepoMap - генерация сжатой карты репозитория в стиле Aider.
Упрощённая версия для MCP сервера.
"""
from collections import defaultdict
from pathlib import Path
from typing import Any

from grep_ast import filename_to_lang
from tree_sitter_language_pack import get_parser

from repository_scanner import RepositoryScanner, ScanConfig

# Загружаем игноры из .ignore пользователя


def load_ignore():
    """Загружает паттерны из .ignore файла пользователя."""
    home = Path.home()
    ignore = home / ".ignore"
    ignored_dirs = set()
    ignored_files = set()
    ignored_patterns = []

    if ignore.exists():
        with open(ignore, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Директории заканчиваются на /
                if line.endswith("/"):
                    ignored_dirs.add(line.rstrip("/"))
                # Файлы с точкой или полным путём
                elif "." in line or "/" in line:
                    ignored_files.add(line)
                # Остальное как паттерн
                else:
                    ignored_dirs.add(line)
                    ignored_patterns.append(f"*{line}*")

    return ignored_dirs, ignored_files, ignored_patterns


IGNORED_DIRS, IGNORED_FILES, IGNORED_PATTERNS = load_ignore()

# Стандартные игноры (всегда игнорируются)
STANDARD_IGNORED_DIRS = {
    ".git", "node_modules", "venv", ".venv", "env", ".env",
    "__pycache__", ".pytest_cache", ".tox", ".nox", ".mypy_cache",
    ".ruff_cache", ".idea", ".vscode", ".vs", "bin", "obj",
    "target", "build", "dist", ".cache", "logs", "tmp", "temp",
}

ARCHITECTURE_CONFIG_NAMES = {
    ".editorconfig",
    ".gitignore",
    "docker-compose.yml",
    "docker-compose.yaml",
    "pyproject.toml",
    "package.json",
    "tsconfig.json",
    "Cargo.toml",
    "go.mod",
    "Makefile",
}
ENTRYPOINT_NAMES = {
    "main.py",
    "app.py",
    "server.py",
    "cli.py",
    "index.ts",
    "main.ts",
    "main.go",
    "main.rs",
    "bootstrap.ts",
    "bootstrap.js",
}
CONTRACT_PARTS = {
    "api",
    "contract",
    "contracts",
    "schema",
    "schemas",
    "protocol",
    "interface",
    "interfaces",
    "dto",
    "routes",
}

ALL_IGNORED_DIRS = IGNORED_DIRS | STANDARD_IGNORED_DIRS


def load_local_ignore(root: Path):
    """Загружает локальный .ignore из корня репозитория."""
    local_ignore = root / ".ignore"
    ignored_dirs = set()
    ignored_files = set()
    ignored_patterns = []

    if local_ignore.exists():
        with open(local_ignore, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.endswith("/"):
                    ignored_dirs.add(line.rstrip("/"))
                elif "." in line or "/" in line:
                    ignored_files.add(line)
                else:
                    ignored_dirs.add(line)
                    ignored_patterns.append(f"*{line}*")

    return ignored_dirs, ignored_files, ignored_patterns


class RepoMap:
    """Генерация сжатой карты репозитория для контекста AI."""

    def __init__(
        self,
        root=None,
        max_tokens=4096,
        scan_config: ScanConfig | None = None,
        indexer: Any | None = None,
    ):
        self.root = Path(root).expanduser().resolve() if root else Path.cwd().resolve()
        self.max_tokens = max_tokens
        self.scan_config = scan_config
        self.indexer = indexer
        self.max_symbols_per_file = 20
        self.max_module_ratio = 0.35

        # Загружаем локальные игноры из репозитория
        local_dirs, local_files, local_patterns = load_local_ignore(self.root)
        self.all_ignored_dirs = ALL_IGNORED_DIRS | local_dirs
        self.all_ignored_files = IGNORED_FILES | local_files
        self.all_ignored_patterns = IGNORED_PATTERNS + local_patterns
        self._tags_cache = {}
        self.last_scan_result = None
        self.last_coverage: dict[str, Any] = {}

    def get_repo_map(self, files=None):
        """
        Генерирует сжатую карту репозитория.

        Args:
            files: Список файлов для включения (если None - все файлы в репозитории)

        Returns:
            Строка с картой репозитория (~4K токенов на 100K+ строк)
        """
        records = self._records(files)
        return self._render(records, symbol_cap=self.max_symbols_per_file)

    def get_architecture_map(self, files=None) -> str:
        """Возвращает bounded macro map с разнообразием модулей."""
        records = self._records(files)
        return self._render(records, symbol_cap=self.max_symbols_per_file)

    def get_symbol_map(self, files=None) -> str:
        """Возвращает более подробную symbol map с тем же safety cap."""
        records = self._records(files)
        return self._render(records, symbol_cap=max(self.max_symbols_per_file, 40))

    def coverage_summary(self) -> dict[str, Any]:
        """Возвращает объяснение bounded selection без чтения содержимого map."""
        return dict(self.last_coverage)

    def _collect_all_files(self):
        """Собирает исходники в пределах сохранённого scan budget."""
        self.last_scan_result = RepositoryScanner(
            self.root, self.scan_config).scan()
        files = [str(path) for path in self.last_scan_result.files]
        known = {Path(path).resolve() for path in files}
        # Configs are architectural evidence even when the parser does not
        # classify them as source files.
        for name in ARCHITECTURE_CONFIG_NAMES:
            candidate = self.root / name
            if candidate.is_file() and candidate.resolve() not in known:
                files.append(str(candidate))
        return files

    def _records(self, files=None) -> list[dict[str, Any]]:
        selected_files = (
            self._collect_all_files()
            if files is None
            else [str(path) for path in files]
        )
        records: list[dict[str, Any]] = []
        for file_name in selected_files:
            path = Path(file_name)
            tags = self._get_tags(path)
            relative = self._relative_name(path)
            roles = self._roles(relative)
            records.append(
                {
                    "file": relative,
                    "tags": tags,
                    "module": self._module_name(relative),
                    "roles": roles,
                    "score": self._architecture_score(relative, tags, roles),
                }
            )
        return records

    def _relative_name(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    @staticmethod
    def _module_name(relative: str) -> str:
        parts = Path(relative).parts
        return parts[0] if len(parts) > 1 else "."

    @staticmethod
    def _roles(relative: str) -> set[str]:
        path = Path(relative)
        name = path.name
        lower_parts = {part.casefold() for part in path.parts}
        roles: set[str] = set()
        if name in ARCHITECTURE_CONFIG_NAMES or name.casefold().startswith("dockerfile"):
            roles.add("config")
        if name in ENTRYPOINT_NAMES or name.casefold() in {"__main__.py", "index.js"}:
            roles.add("entrypoint")
        if lower_parts & CONTRACT_PARTS or any(
            token in path.stem.casefold()
            for token in ("schema", "contract", "protocol", "interface")
        ):
            roles.add("contract")
        if any(
            token in path.stem.casefold()
            for token in ("route", "worker", "bootstrap", "register")
        ):
            roles.add("control")
        return roles

    def _architecture_score(
        self, relative: str, tags: list[dict[str, Any]], roles: set[str]
    ) -> float:
        score = min(2.0, len(tags) / 20)
        score += 5.0 * len(roles)
        if self.indexer is not None:
            graphs = getattr(self.indexer, "graphs", None)
            snapshot = getattr(graphs, "snapshot", None)
            if callable(snapshot):
                graph = snapshot()
                imports = graph.get("import_graph", {})
                score += min(2.0, len(imports.get(str(self.root / relative), [])) / 5)
                score += min(2.0, sum(1 for values in imports.values() if relative in str(values)))
        return score

    def _select_records(
        self, records: list[dict[str, Any]], symbol_cap: int
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not records:
            return [], {"candidate_files": 0, "selected_files": 0, "modules": {}}

        by_module: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            by_module[record["module"]].append(record)
        for values in by_module.values():
            values.sort(key=lambda item: (-item["score"], item["file"]))

        selected: list[dict[str, Any]] = []
        selected_ids: set[str] = set()
        budget_tokens = max(1, int(self.max_tokens))
        module_budget = max(1, int(budget_tokens * self.max_module_ratio))
        module_tokens: dict[str, int] = defaultdict(int)

        def estimated_tokens(record: dict[str, Any]) -> int:
            count = min(symbol_cap, len(record["tags"]))
            return max(8, 4 + count * 4)

        # Mandatory roles first, but still bounded by the global budget.
        for role in ("config", "entrypoint", "contract", "control"):
            candidates = [record for record in records if role in record["roles"]]
            candidates.sort(key=lambda item: (-item["score"], item["file"]))
            for record in candidates[: max(1, len(by_module))]:
                cost = estimated_tokens(record)
                module = record["module"]
                if record["file"] in selected_ids or sum(
                    estimated_tokens(item) for item in selected
                ) + cost > budget_tokens:
                    continue
                if module_tokens[module] + cost > module_budget and selected:
                    continue
                selected.append(record)
                selected_ids.add(record["file"])
                module_tokens[module] += cost

        # Weighted round-robin prevents a single giant module from filling the map.
        while len(selected_ids) < len(records):
            progressed = False
            for module in sorted(by_module):
                candidate = next(
                    (item for item in by_module[module] if item["file"] not in selected_ids),
                    None,
                )
                if candidate is None:
                    continue
                cost = estimated_tokens(candidate)
                total = sum(estimated_tokens(item) for item in selected)
                if total + cost > budget_tokens:
                    continue
                if module_tokens[module] + cost > module_budget and len(by_module) > 1:
                    continue
                selected.append(candidate)
                selected_ids.add(candidate["file"])
                module_tokens[module] += cost
                progressed = True
            if not progressed:
                break

        candidate_modules = sorted(by_module)
        selected_modules = sorted({record["module"] for record in selected})
        summary = {
            "candidate_files": len(records),
            "selected_files": len(selected),
            "candidate_modules": candidate_modules,
            "represented_modules": selected_modules,
            "omitted_modules": [
                module for module in candidate_modules if module not in selected_modules
            ],
            "mandatory_roles_found": sorted(
                {role for record in records for role in record["roles"]}
            ),
            "mandatory_roles_selected": sorted(
                {role for record in selected for role in record["roles"]}
            ),
            "symbol_cap_per_file": symbol_cap,
            "module_budget_ratio": self.max_module_ratio,
            "module_token_estimates": dict(sorted(module_tokens.items())),
        }
        return selected, summary

    def _render(self, records: list[dict[str, Any]], symbol_cap: int) -> str:
        selected, summary = self._select_records(records, symbol_cap)
        self.last_coverage = summary
        if not selected:
            return ""
        output = ["# Booster Repo Map", "", "## Coverage", ""]
        output.extend(f"- {key}: {value}" for key, value in summary.items())
        output.extend(["", "## Symbols", ""])
        for record in sorted(selected, key=lambda item: (item["module"], item["file"])):
            output.append(f"{record['file']}:")
            if record["roles"]:
                output.append(f"  roles: {', '.join(sorted(record['roles']))}")
            tags = sorted(record["tags"], key=lambda item: item["line"])[:symbol_cap]
            for tag in tags:
                output.append(f"  def {tag['name']} (line {tag['line']})")
            omitted = len(record["tags"]) - len(tags)
            if omitted > 0:
                output.append(f"  +{omitted} symbols omitted by per-file cap")
            output.append("")
        return "\n".join(output)

    def _get_tags(self, fname):
        """Извлекает теги (функции, классы) из файла."""
        fname = Path(fname)
        if not fname.is_absolute():
            fname = self.root / fname

        lang = filename_to_lang(str(fname))
        if not lang:
            return []

        try:
            parser = get_parser(lang)
        except Exception:
            return []

        try:
            code_bytes = fname.read_bytes()
        except Exception:
            return []

        tree = parser.parse(code_bytes)
        root = tree.root_node

        tags = []
        rel_fname = (
            fname.relative_to(self.root).as_posix()
            if fname.is_relative_to(self.root)
            else str(fname)
        )

        # Обход AST для поиска определений
        self._traverse_tree(root, code_bytes, rel_fname, tags)

        return tags

    def _traverse_tree(self, node, code_bytes, rel_fname, tags, depth=0):
        """Итеративный обход AST для поиска определений."""
        if depth > 500:
            return

        stack = [(node, depth)]

        while stack:
            current_node, current_depth = stack.pop()

            if current_depth > 500:
                continue

            # Проверяем тип узла
            node_type = current_node.type

            # Ищем определения функций, классов, методов
            if "definition" in node_type or node_type in [
                "function_definition",
                "class_definition",
                "class_declaration",
                "function_declaration",
            ]:
                name_node = self._find_name_node(current_node)
                if name_node:
                    name = code_bytes[name_node.start_byte:name_node.end_byte].decode(
                        "utf-8", errors="ignore")
                    tags.append({
                        "file": rel_fname,
                        "name": name,
                        "line": current_node.start_point[0],
                        "kind": "def"
                    })

            # Добавляем детей в стек
            for child in reversed(current_node.children):
                stack.append((child, current_depth + 1))

    def _find_name_node(self, node):
        """Ищет узел имени в дереве."""
        # Пробуем получить по полю имени
        name_node = node.child_by_field_name("name")
        if name_node:
            return name_node

        # Ищем вручную
        for child in node.children:
            if child.type in ["identifier", "type_identifier", "property_identifier"]:
                return child

        return None

    def _build_tree(self, tags):
        """Строит дерево репозитория из тегов с ограничением по токенам."""
        if not tags:
            return ""

        # Группируем теги по файлам
        by_file = defaultdict(list)
        for tag in tags:
            by_file[tag["file"]].append(tag)

        output = []
        total_tokens = 0

        for fname, file_tags in sorted(by_file.items()):
            # Ограничиваем по токенам
            if total_tokens >= self.max_tokens:
                break

            # Формируем секцию для файла
            section = f"\n{fname}:\n"

            # Добавляем определения
            defs = [t for t in file_tags if t["kind"] == "def"]
            for tag in sorted(defs, key=lambda x: x["line"]):
                line_info = f"  {tag['kind']} {tag['name']} (line {tag['line']})\n"
                section += line_info

            # Проверяем размер
            section_tokens = len(section.split()) * 4  # грубая оценка
            if total_tokens + section_tokens > self.max_tokens:
                break

            output.append(section)
            total_tokens += section_tokens

        return "".join(output) if output else ""
