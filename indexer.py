import hashlib
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from chunker import semantic_chunks
from embedder import Embedder
from graphs import Graphs
from parser_router import ParserRouter
from repository_scanner import RepositoryScanner, ScanResult
from vector_index import VectorIndex


class IndexCancelled(RuntimeError):
    """Индексация остановлена на безопасной границе."""


@dataclass
class IndexGeneration:
    repository: str
    generation_id: str
    base_generation_id: str | None
    scan_result: ScanResult
    symbols: dict[str, list[dict[str, Any]]]
    graphs: Graphs
    vector: VectorIndex


class RepoIndexer:
    def __init__(self, repos: list[str], on_index_complete: Callable[[str], None] | None = None):
        self.repos: list[str] = repos
        self.router: ParserRouter = ParserRouter()
        self.graphs: Graphs = Graphs()
        self.embedder: Embedder = Embedder()
        self.vector: VectorIndex = VectorIndex()
        self.symbols: dict[str, list[dict[str, Any]]] = {}
        self.generation_id: str | None = None
        self.generation_metadata: dict[str, Any] = {
            "generation_id": None,
            "repository": None,
            "ready": False,
            "stale": False,
            "stale_reasons": [],
        }
        # Callback после индексации репозитория
        self.on_index_complete = on_index_complete
        self._lock = threading.RLock()

    def _operation_lock(self) -> threading.RLock:
        # Some legacy tests construct a lightweight instance with __new__.
        lock = getattr(self, "_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._lock = lock
        return lock

    @property
    def operation_lock(self) -> threading.RLock:
        """Shared lock for integrations that must read the index consistently."""
        return self._operation_lock()

    def extract_data(
        self,
        tree: Any,
        code_bytes: bytes,
        path_str: str,
        graphs: Graphs | None = None,
    ) -> list[dict[str, Any]]:
        target_graphs = graphs or self.graphs
        root = tree.root_node
        symbols: list[dict[str, Any]] = []
        MAX_DEPTH = 500

        # Итеративный обход через стек (защита от RecursionError)
        stack: list[tuple[Any, str | None, int]] = [(root, None, 0)]  # (node, current_scope, depth)

        while stack:
            node, current_scope, depth = stack.pop()

            if depth > MAX_DEPTH:
                continue

            scope = current_scope

            # Парсинг функций и классов (symbols)
            if any(t in node.type for t in ["function", "class", "method"]):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = code_bytes[name_node.start_byte : name_node.end_byte].decode(
                        "utf8", errors="ignore"
                    )
                    symbols.append(
                        {
                            "name": name,
                            "start": node.start_point[0],
                            "end": node.end_point[0],
                            "file": path_str,
                        }
                    )
                    scope = name  # Устанавливаем текущий скоуп для графа вызовов

            # Парсинг импортов (import graph)
            if "import" in node.type:
                imp_text = code_bytes[node.start_byte : node.end_byte].decode(
                    "utf8", errors="ignore"
                )
                target_graphs.add_import(path_str, imp_text)

            # Парсинг вызовов (call graph)
            if "call" in node.type:
                func_node = node.child_by_field_name("function")
                if func_node and current_scope:
                    callee = code_bytes[func_node.start_byte : func_node.end_byte].decode(
                        "utf8", errors="ignore"
                    )
                    target_graphs.add_call(path_str, current_scope, callee)

            # Добавляем детей в стек (в обратном порядке для сохранения порядка обхода)
            for child in reversed(node.children):
                stack.append((child, scope, depth + 1))

        return symbols

    def index_file(self, path: Path) -> None:
        with self._operation_lock():
            self._index_file_unlocked(path)

    def _index_file_unlocked(self, path: Path) -> None:
        self._index_file_in_state(path, self.vector, self.graphs, self.symbols)

    def _index_file_in_state(
        self,
        path: Path,
        vector: VectorIndex,
        graphs: Graphs,
        symbols: dict[str, list[dict[str, Any]]],
        *,
        cancel: Callable[[], bool] | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> int:
        path = Path(path).expanduser().resolve()
        parser = self.router.get(path)
        if not parser:
            return 0

        if cancel is not None and cancel():
            raise IndexCancelled("indexing cancelled")

        try:
            code_str = path.read_text(encoding="utf8", errors="ignore")
        except Exception:
            return 0

        code_bytes = bytes(code_str, "utf8")
        tree = parser.parse(code_bytes)
        path_str = str(path)

        # Очистка старых данных файла (для Watchdog)
        vector.remove_file(path_str)
        graphs.clear_file(path_str)

        file_symbols = self.extract_data(tree, code_bytes, path_str, graphs)
        symbols[path_str] = file_symbols
        if progress is not None:
            progress("graph")

        chunks: list[str] = semantic_chunks(file_symbols, code_str)
        for chunk in chunks:
            if cancel is not None and cancel():
                raise IndexCancelled("indexing cancelled")
            vec = self.embedder.embed(chunk)
            vector.add(vec, {"file": path_str, "chunk": chunk})
        if progress is not None:
            progress("embed")
        return len(chunks)

    def _staging_state(
        self, repo_path: Path
    ) -> tuple[dict[str, list[dict[str, Any]]], Graphs, VectorIndex]:
        with self._operation_lock():
            symbols = {
                file_path: [dict(symbol) for symbol in file_symbols]
                for file_path, file_symbols in self.symbols.items()
                if not Path(file_path).resolve().is_relative_to(repo_path)
            }
            graphs = self.graphs.clone()
            vector = self.vector.clone()
            target_files = [
                file_path
                for file_path in list(vector.file_ids)
                if Path(file_path).resolve().is_relative_to(repo_path)
            ]
            for file_path in target_files:
                vector.remove_file(file_path)
                graphs.clear_file(file_path)
        return symbols, graphs, vector

    def build_generation(
        self,
        repo: str,
        *,
        cancel: Callable[[], bool] | None = None,
        progress: Callable[[str, int, int | None], None] | None = None,
    ) -> IndexGeneration:
        """Строит candidate generation без мутации ready state."""
        repo_path = Path(repo).expanduser().resolve()

        def scan_progress(phase: str, processed: int, total: int | None) -> None:
            if progress is not None:
                progress(phase, processed, total)

        scan_result = RepositoryScanner(repo_path).scan(
            progress=scan_progress,
            cancel=cancel,
        )
        if cancel is not None and cancel():
            raise IndexCancelled("indexing cancelled")

        symbols, graphs, vector = self._staging_state(repo_path)
        total = len(scan_result.files)
        for position, file_path in enumerate(scan_result.files, start=1):
            if cancel is not None and cancel():
                raise IndexCancelled("indexing cancelled")
            if progress is not None:
                progress("parse", position, total)
            self._index_file_in_state(
                file_path,
                vector,
                graphs,
                symbols,
                cancel=cancel,
                progress=lambda phase, current=position: progress(phase, current, total)
                if progress is not None
                else None,
            )

        manifest_payload = repr(sorted(scan_result.file_manifest.items())).encode("utf-8")
        generation_id = hashlib.sha256(
            manifest_payload + uuid.uuid4().hex.encode("ascii")
        ).hexdigest()[:24]
        return IndexGeneration(
            repository=str(repo_path),
            generation_id=generation_id,
            base_generation_id=self.generation_id,
            scan_result=scan_result,
            symbols=symbols,
            graphs=graphs,
            vector=vector,
        )

    def promote_generation(self, generation: IndexGeneration) -> None:
        """Публикует candidate коротким pointer swap."""
        with self._operation_lock():
            self.symbols = generation.symbols
            self.graphs = generation.graphs
            self.vector = generation.vector
            self.generation_id = generation.generation_id
            self.generation_metadata = {
                "generation_id": generation.generation_id,
                "base_generation_id": generation.base_generation_id,
                "repository": generation.repository,
                "ready": True,
                "stale": False,
                "stale_reasons": [],
                "source_manifest": generation.scan_result.file_manifest,
                "files_indexed": len(generation.scan_result.files),
            }

    def full_index(self) -> None:
        for repo in self.repos:
            self.index_repo(repo)

    def index_repo(self, repo: str) -> ScanResult:
        """Индексирует один репозиторий в пределах настроенных scan-budget."""
        repo_path = Path(repo).expanduser().resolve()
        scan_result = RepositoryScanner(repo_path).scan()
        scanned_files = {str(Path(path).expanduser().resolve()) for path in scan_result.files}
        with self._operation_lock():
            symbols = getattr(self, "symbols", {})
            stale_files = [
                file_path
                for file_path in symbols
                if Path(file_path).resolve().is_relative_to(repo_path)
                and file_path not in scanned_files
            ]
            for file_path in stale_files:
                self._remove_file_unlocked(file_path)
            for file_path in scan_result.files:
                # Keep the public hook compatible with legacy integrations/tests.
                self.index_file(file_path)

            # Save the scan report before the completion callback captures a snapshot.
            scan_result.save_report()

            # Вызываем callback после индексации репозитория.
            if self.on_index_complete:
                self.on_index_complete(str(repo_path))

        return scan_result

    def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        vec = self.embedder.embed(query)
        with self._operation_lock():
            results = self.vector.search(vec, k=k)
        return [result for result in results if Path(str(result.get("file", ""))).is_file()]

    def hybrid_search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        """Ищет код, комбинируя семантический и точный lexical-поиск."""
        vec = self.embedder.embed(query)
        with self._operation_lock():
            results = self.vector.hybrid_search(vec, query, k=k)
        return [result for result in results if Path(str(result.get("file", ""))).is_file()]

    def _remove_file_unlocked(self, file_path: str) -> None:
        self.vector.remove_file(file_path)
        self.graphs.clear_file(file_path)
        self.symbols.pop(file_path, None)

    def remove_file(self, path: str | Path) -> None:
        """Removes all index state for one file, safely for watcher callbacks."""
        normalized = str(Path(path).expanduser().resolve())
        with self._operation_lock():
            matching = [
                file_path
                for file_path in self.symbols
                if Path(file_path).expanduser().resolve() == Path(normalized)
            ]
            for file_path in matching or [normalized]:
                self._remove_file_unlocked(file_path)

    def remove_repo(self, repo: str | Path) -> None:
        """Removes all indexed files belonging to one repository."""
        root = Path(repo).expanduser().resolve()
        with self._operation_lock():
            files = [
                file_path
                for file_path in self.symbols
                if Path(file_path).expanduser().resolve().is_relative_to(root)
            ]
            for file_path in files:
                self._remove_file_unlocked(file_path)

    def symbols_snapshot(self) -> dict[str, list[dict[str, Any]]]:
        with self._operation_lock():
            return {
                file_path: [dict(symbol) for symbol in symbols]
                for file_path, symbols in self.symbols.items()
            }

    def find_symbols(self, name: str) -> list[dict[str, Any]]:
        with self._operation_lock():
            return [
                dict(symbol)
                for symbols in self.symbols.values()
                for symbol in symbols
                if symbol.get("name") == name
            ]

    def stats(self) -> dict[str, Any]:
        with self._operation_lock():
            return {
                "files_indexed": len(self.symbols),
                "vectors_in_faiss": int(self.vector.index.ntotal),
                "generation_id": self.generation_id,
            }

    def index_health(self) -> dict[str, Any]:
        with self._operation_lock():
            return dict(self.generation_metadata)

    def mark_stale(self, reason: str, path: str | None = None) -> dict[str, Any]:
        """Помечает ready generation stale до завершения следующего rebuild."""
        with self._operation_lock():
            reasons = list(self.generation_metadata.get("stale_reasons", []))
            value = reason if path is None else f"{reason}:{path}"
            if value not in reasons:
                reasons.append(value)
            self.generation_metadata["stale"] = True
            self.generation_metadata["stale_reasons"] = reasons[-20:]
            return dict(self.generation_metadata)
