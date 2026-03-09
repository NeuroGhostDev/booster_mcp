class Graphs:
    def __init__(self):
        self.call_graph = {}
        self.import_graph = {}
        
        # Индексы для инкрементального обновления
        self.file_calls = {} 
        self.file_imports = {}

    def clear_file(self, file):
        if file in self.file_imports:
            self.import_graph[file] =[]
            del self.file_imports[file]
            
        if file in self.file_calls:
            for caller, callee in self.file_calls[file]:
                if caller in self.call_graph and callee in self.call_graph[caller]:
                    self.call_graph[caller].remove(callee)
            del self.file_calls[file]

    def add_call(self, file, caller, callee):
        self.call_graph.setdefault(caller, set()).add(callee)
        self.file_calls.setdefault(file,[]).append((caller, callee))

    def add_import(self, file, module):
        if file not in self.import_graph:
            self.import_graph[file] = []
        self.import_graph[file].append(module)
        self.file_imports.setdefault(file, set()).add(module)

    def calls(self, symbol):
        return list(self.call_graph.get(symbol,[]))

    def imports(self, file):
        return self.import_graph.get(file,[])
