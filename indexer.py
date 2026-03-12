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
        import os
        MAX_DEPTH = 15
        
        for repo in self.repos:
            repo_path = Path(repo).expanduser().resolve()
            
            # Чтение игноров из .ignore
            current_ignores = set(IGNORED_DIRS)
            ignore_file = repo_path / ".ignore"
            if ignore_file.exists():
                try:
                    with open(ignore_file, "r", encoding="utf-8") as f:
                        for line in f:
                            cleaned = line.strip()
                            if cleaned and not cleaned.startswith("#"):
                                current_ignores.add(cleaned.strip('/')) # Убираем слэши для os.walk
                except Exception:
                    pass

            for root, dirs, files in os.walk(repo_path):
                # Исключаем директории на лету (os.walk не зайдет в удаленные из dirs)
                dirs[:] = [d for d in dirs if d not in current_ignores and not d.startswith('.')]
                
                # Проверка глубины вложенности
                try:
                    rel_path = Path(root).relative_to(repo_path)
                    depth = len(rel_path.parts)
                    if depth >= MAX_DEPTH:
                        dirs[:] = []
                        continue
                except ValueError:
                    continue
                    
                for file_name in files:
                    # Игнорируем файлы, которые начинаются с точки или в current_ignores (например __pycache__ файлы)
                    if file_name.startswith('.') or file_name in current_ignores:
                        continue
                        
                    file_path = Path(root) / file_name
                    self.index_file(file_path)

            # Вызываем callback после индексации каждого репозитория
            if self.on_index_complete:
                self.on_index_complete(repo)

    def search(self, query):
        vec = self.embedder.embed(query)
        return self.vector.search(vec)
