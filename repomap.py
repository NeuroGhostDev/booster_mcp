"""
RepoMap - генерация сжатой карты репозитория в стиле Aider.
Упрощённая версия для MCP сервера.
"""
import os
import fnmatch
from pathlib import Path
from collections import defaultdict

from grep_ast import filename_to_lang
from tree_sitter_language_pack import get_parser

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

    def __init__(self, root=None, max_tokens=4096):
        self.root = Path(root) if root else Path.cwd()
        self.max_tokens = max_tokens

        # Загружаем локальные игноры из репозитория
        local_dirs, local_files, local_patterns = load_local_ignore(self.root)
        self.all_ignored_dirs = ALL_IGNORED_DIRS | local_dirs
        self.all_ignored_files = IGNORED_FILES | local_files
        self.all_ignored_patterns = IGNORED_PATTERNS + local_patterns
        self._tags_cache = {}

    def get_repo_map(self, files=None):
        """
        Генерирует сжатую карту репозитория.

        Args:
            files: Список файлов для включения (если None - все файлы в репозитории)

        Returns:
            Строка с картой репозитория (~4K токенов на 100K+ строк)
        """
        if files is None:
            files = self._collect_all_files()

        if not files:
            return ""

        # Собираем теги (функции, классы, методы) из всех файлов
        all_tags = []
        for file in files:
            tags = self._get_tags(file)
            all_tags.extend(tags)

        # Генерируем дерево с ограничением по токенам
        tree = self._build_tree(all_tags)

        return tree

    def _collect_all_files(self):
        """Собирает все файлы в репозитории, игнорируя указанные директории."""
        files = []
        for file in self.root.rglob("*"):
            try:
                if not file.is_file():
                    continue
            except (PermissionError, OSError):
                continue

            # Проверка игнорируемых директорий
            if any(part in self.all_ignored_dirs for part in file.parts):
                continue

            # Проверка игнорируемых файлов
            if file.name in self.all_ignored_files:
                continue

            # Проверка паттернов
            skip = False
            for pattern in self.all_ignored_patterns:
                if fnmatch.fnmatch(file.name, pattern):
                    skip = True
                    break
            if skip:
                continue

            files.append(str(file))
        return files

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
            code = code_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return []

        tree = parser.parse(code_bytes)
        root = tree.root_node

        tags = []
        rel_fname = str(fname.relative_to(self.root)) if fname.is_relative_to(
            self.root) else str(fname)

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
            if "definition" in node_type or node_type in ["function_definition", "class_definition", "class_declaration", "function_declaration"]:
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
