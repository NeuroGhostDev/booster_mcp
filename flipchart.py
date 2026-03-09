"""
Flipchart MCP — флипчарт для дебага сложных систем
Генерирует Mermaid-диаграммы, трассировку вызовов и заметки
"""
import json
from pathlib import Path
from typing import Optional
from collections import deque


class Flipchart:
    """Управляет флипчартом: диаграммы, заметки, трассировки"""
    
    def __init__(self, indexer):
        self.indexer = indexer
        self.sessions = {}  # session_id -> {notes, diagrams, traces}
    
    def generate_call_graph_mermaid(self, symbol: str, max_depth: int = 3) -> str:
        """Генерирует Mermaid-диаграмму вызовов для символа"""
        visited = set()
        edges = []
        queue = deque([(symbol, 0)])

        while queue:
            current, depth = queue.popleft()
            if depth > max_depth or current in visited:
                continue
            visited.add(current)

            calls = self.indexer.graphs.calls(current)
            for call in calls:
                # calls() возвращает список строк
                target = call if isinstance(call, str) else call.get("name", call.get("symbol", "unknown"))
                edges.append(f"    {self._safe_id(current)} --> {self._safe_id(target)}")
                queue.append((target, depth + 1))
        
        mermaid = ["graph LR"]
        mermaid.append(f"    %% Call graph для: {symbol}")
        mermaid.extend(edges)
        return "\n".join(mermaid)
    
    def generate_import_graph_mermaid(self, file_path: str) -> str:
        """Генерирует Mermaid-диаграмму импортов для файла"""
        imports = self.indexer.graphs.imports(file_path)
        
        mermaid = ["graph LR"]
        mermaid.append(f"    %% Import graph для: {Path(file_path).name}")
        
        file_id = self._safe_id(Path(file_path).name)
        for imp in imports:
            imp_path = imp.get("path", imp.get("module", "unknown"))
            imp_id = self._safe_id(Path(imp_path).name if imp_path else "unknown")
            mermaid.append(f"    {file_id} --> {imp_id}")
        
        return "\n".join(mermaid)
    
    def generate_sequence_diagram(self, start_symbol: str, depth: int = 5) -> str:
        """Генерирует Sequence-диаграмму выполнения"""
        trace = self._trace_execution(start_symbol, depth)
        
        participants = set()
        messages = []
        
        for step in trace:
            caller = self._safe_id(step.get("caller", "unknown"))
            callee = self._safe_id(step.get("callee", "unknown"))
            participants.add(caller)
            participants.add(callee)
            messages.append(f"    {caller}->>{callee}: {step.get('method', '')}")
        
        mermaid = ["sequenceDiagram"]
        for p in sorted(participants):
            mermaid.append(f"    participant {p}")
        mermaid.extend(messages)
        
        return "\n".join(mermaid)
    
    def _trace_execution(self, symbol: str, max_depth: int) -> list[dict]:
        """Трассирует выполнение от начального символа"""
        trace = []
        visited = set()
        stack = [(None, symbol, 0)]
        
        while stack:
            caller, current, depth = stack.pop()
            if depth > max_depth or current in visited:
                continue
            visited.add(current)
            
            if caller:
                trace.append({
                    "caller": caller,
                    "callee": current,
                    "method": current,
                    "depth": depth
                })
            
            calls = self.indexer.graphs.calls(current)
            for call in reversed(calls):  # reversed для правильного порядка стека
                # calls() возвращает список строк
                target = call if isinstance(call, str) else call.get("name", call.get("symbol", "unknown"))
                stack.append((current, target, depth + 1))
        
        return trace
    
    def _safe_id(self, name: str) -> str:
        """Делает безопасный идентификатор для Mermaid"""
        # Заменяем недопустимые символы
        safe = name.replace(".", "_").replace("-", "_").replace(" ", "_")
        safe = "".join(c for c in safe if c.isalnum() or c == "_")
        # Если начинается с цифры, добавляем префикс
        if safe and safe[0].isdigit():
            safe = "id_" + safe
        return safe or "unknown"
    
    def create_session(self, session_id: str, symbols: list[str]) -> dict:
        """Создаёт сессию дебага с отслеживаемыми символами"""
        self.sessions[session_id] = {
            "symbols": symbols,
            "notes": [],
            "diagrams": [],
            "traces": []
        }
        
        # Автогенерация начальных диаграмм
        for symbol in symbols:
            diagram = self.generate_call_graph_mermaid(symbol)
            self.sessions[session_id]["diagrams"].append({
                "type": "call_graph",
                "symbol": symbol,
                "content": diagram
            })
        
        return {"success": f"Сессия {session_id} создана", "symbols": symbols}
    
    def add_note(self, session_id: str, label: str, content: str, 
                 symbols: Optional[list[str]] = None) -> dict:
        """Добавляет заметку на флипчарт"""
        if session_id not in self.sessions:
            return {"error": f"Сессия не найдена: {session_id}"}
        
        note = {
            "label": label,
            "content": content,
            "symbols": symbols or [],
            "timestamp": str(Path.home())
        }
        self.sessions[session_id]["notes"].append(note)
        return {"success": "Заметка добавлена", "note_id": len(self.sessions[session_id]["notes"]) - 1}
    
    def get_board(self, session_id: str) -> dict:
        """Возвращает весь флипчарт сессии"""
        if session_id not in self.sessions:
            return {"error": f"Сессия не найдена: {session_id}"}
        
        session = self.sessions[session_id]
        return {
            "session_id": session_id,
            "symbols": session["symbols"],
            "notes_count": len(session["notes"]),
            "diagrams_count": len(session["diagrams"]),
            "notes": session["notes"],
            "diagrams": session["diagrams"]
        }
    
    def quick_debug(self, symbol: str, max_depth: int = 3) -> dict:
        """
        Быстрый дебаг: одна команда → полный флипчарт
        1. Call graph в Mermaid
        2. Семантический контекст
        3. Связанные символы
        """
        # Call graph
        call_graph = self.generate_call_graph_mermaid(symbol, max_depth)

        # Семантический поиск (search принимает строку)
        semantic = self.indexer.search(symbol)
        
        # Символы из того же файла
        related = []
        for file_path, syms in self.indexer.symbols.items():
            for sym in syms:
                if sym.get("name") == symbol:
                    related = [s for s in syms if s.get("name") != symbol]
                    break
            if related:
                break
        
        return {
            "symbol": symbol,
            "call_graph_mermaid": call_graph,
            "semantic_context": semantic,
            "related_symbols": related[:10],
            "files_searched": len(self.indexer.symbols)
        }


# Инструменты для MCP
def setup_flipchart_tools(mcp, indexer):
    """Регистрирует инструменты flipchart в MCP сервере"""
    flipchart = Flipchart(indexer)
    
    @mcp.tool()
    def flipchart_quick_debug(symbol: str, max_depth: int = 3):
        """
        Быстрый дебаг символа: генерирует Mermaid call graph + семантический контекст.
        Идеально для анализа сложных систем.
        """
        return flipchart.quick_debug(symbol, max_depth)
    
    @mcp.tool()
    def flipchart_create_session(session_id: str, symbols: list[str]):
        """
        Создаёт сессию дебага для отслеживания группы символов.
        Автоматически генерирует начальные диаграммы.
        """
        return flipchart.create_session(session_id, symbols)
    
    @mcp.tool()
    def flipchart_add_note(session_id: str, label: str, content: str, 
                           symbols: Optional[list[str]] = None):
        """
        Добавляет заметку-инсайт на флипчарт сессии.
        Можно привязать к конкретным символам.
        """
        return flipchart.add_note(session_id, label, content, symbols)
    
    @mcp.tool()
    def flipchart_get_board(session_id: str):
        """
        Возвращает полный флипчарт сессии: все диаграммы и заметки.
        """
        return flipchart.get_board(session_id)
    
    @mcp.tool()
    def flipchart_call_graph(symbol: str, max_depth: int = 5):
        """
        Генерирует Mermaid-диаграмму вызовов для символа.
        """
        return {"mermaid": flipchart.generate_call_graph_mermaid(symbol, max_depth)}
    
    @mcp.tool()
    def flipchart_sequence_diagram(symbol: str, depth: int = 5):
        """
        Генерирует Sequence-диаграмму выполнения от символа.
        """
        return {"mermaid": flipchart.generate_sequence_diagram(symbol, depth)}
    
    return flipchart
