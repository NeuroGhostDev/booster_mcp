class Graphs:
    def __init__(self) -> None:
        self.call_graph: dict[str, set[str]] = {}
        self.import_graph: dict[str, list[str]] = {}

        # Индексы для инкрементального обновления
        self.file_calls: dict[str, list[tuple[str, str]]] = {}
        self.file_imports: dict[str, set[str]] = {}

    def clear_file(self, file: str) -> None:
        if file in self.file_imports:
            self.import_graph[file] = []
            del self.file_imports[file]

        if file in self.file_calls:
            for caller, callee in self.file_calls[file]:
                if caller in self.call_graph and callee in self.call_graph[caller]:
                    self.call_graph[caller].remove(callee)
            del self.file_calls[file]

    def add_call(self, file: str, caller: str, callee: str) -> None:
        self.call_graph.setdefault(caller, set()).add(callee)
        self.file_calls.setdefault(file, []).append((caller, callee))

    def add_import(self, file: str, module: str) -> None:
        if file not in self.import_graph:
            self.import_graph[file] = []
        self.import_graph[file].append(module)
        self.file_imports.setdefault(file, set()).add(module)

    def calls(self, symbol: str) -> list[str]:
        return list(self.call_graph.get(symbol, []))

    def imports(self, file: str) -> list[str]:
        return self.import_graph.get(file, [])
