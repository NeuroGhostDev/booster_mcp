from threading import Lock
from typing import Any, cast

from sentence_transformers import SentenceTransformer


class Embedder:
    def __init__(self) -> None:
        # Веса не должны загружаться при импорте MCP server или CLI.
        self.model: Any | None = None
        self._lock = Lock()

    def _ensure_model(self) -> Any:
        if self.model is None:
            with self._lock:
                if self.model is None:
                    self.model = SentenceTransformer("all-MiniLM-L6-v2")
        return self.model

    def embed(self, text: str) -> Any:
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> Any:
        model = cast(Any, self._ensure_model())
        return model.encode(texts, convert_to_numpy=True)
