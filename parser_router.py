from pathlib import Path
from typing import Any

from tree_sitter_language_pack import get_parser

EXT_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp"
}


class ParserRouter:
    def __init__(self) -> None:
        self.parsers: dict[str, Any] = {}

    def get(self, path: str | Path) -> Any | None:
        path = Path(path) if isinstance(path, str) else path
        ext = path.suffix
        if ext not in EXT_MAP:
            return None

        lang = EXT_MAP[ext]
        if lang not in self.parsers:
            self.parsers[lang] = get_parser(lang)

        return self.parsers[lang]
