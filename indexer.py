from pathlib import Path
from parser_router import ParserRouter
from graphs import Graphs
from embedder import Embedder
from vector_index import VectorIndex
from chunker import semantic_chunks

IGNORED_DIRS = {".git", "node_modules", "venv", "env", "__pycache__", ".idea", ".vscode", "dist", "build"}

class RepoIndexer:
    def __init__(self, repos, on_index_complete=None):
        self.repos = repos
        self.router = ParserRouter()
        self.graphs = Graphs()
        self.embedder = Embedder()
        self.vector = VectorIndex()
        self.symbols = {}
        self.on_index_complete = on_index_complete  # Callback после индексации репозитория

    def extract_data(self, tree, code_bytes, path_str):
        root = tree.root_node
        symbols = []
        MAX_DEPTH = 500

        # Итеративный обход через стек (защита от RecursionError)
        stack = [(root, None, 0)]  # (node, current_scope, depth)

        while stack:
            node, current_scope, depth = stack.pop()

            if depth > MAX_DEPTH:
                continue

            scope = current_scope

            # Парсинг функций и классов (symbols)
            if any(t in node.type for t in ["function", "class", "method"]):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = code_bytes[name_node.start_byte:name_node.end_byte].decode("utf8", errors="ignore")
                    symbols.append({
                        "name": name,
                        "start": node.start_point[0],
                        "end": node.end_point[0],
                        "file": path_str
                    })
                    scope = name  # Устанавливаем текущий скоуп для графа вызовов

            # Парсинг импортов (import graph)
            if "import" in node.type:
                imp_text = code_bytes[node.start_byte:node.end_byte].decode("utf8", errors="ignore")
                self.graphs.add_import(path_str, imp_text)

            # Парсинг вызовов (call graph)
            if "call" in node.type:
                func_node = node.child_by_field_name("function")
                if func_node and current_scope:
                    callee = code_bytes[func_node.start_byte:func_node.end_byte].decode("utf8", errors="ignore")
                    self.graphs.add_call(path_str, current_scope, callee)

            # Добавляем детей в стек (в обратном порядке для сохранения порядка обхода)
            for child in reversed(node.children):
                stack.append((child, scope, depth + 1))

        return symbols

    def index_file(self, path):
        parser = self.router.get(path)
        if not parser:
            return

        try:
            code_str = path.read_text(encoding="utf8", errors="ignore")
        except Exception:
            return

        code_bytes = bytes(code_str, "utf8")
        tree = parser.parse(code_bytes)
        path_str = str(path)

        # Очистка старых данных файла (для Watchdog)
        self.vector.remove_file(path_str)
        self.graphs.clear_file(path_str)

        symbols = self.extract_data(tree, code_bytes, path_str)
        self.symbols[path_str] = symbols

        chunks = semantic_chunks(symbols, code_str)
        for chunk in chunks:
            vec = self.embedder.embed(chunk)
            self.vector.add(vec, {
                "file": path_str,
                "chunk": chunk
            })

    def full_index(self):
        for repo in self.repos:
            for file in Path(repo).rglob("*"):
                if not file.is_file():
                    continue
                if any(part in IGNORED_DIRS for part in file.parts):
                    continue
                self.index_file(file)

            # Вызываем callback после индексации каждого репозитория
            if self.on_index_complete:
                self.on_index_complete(repo)

    def search(self, query):
        vec = self.embedder.embed(query)
        return self.vector.search(vec)
