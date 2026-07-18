from typing import Any, cast

from sentence_transformers import SentenceTransformer


class Embedder:
    def __init__(self) -> None:
        # Оптимальная модель для базового семантического поиска
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def embed(self, text: str) -> Any:
        model = cast(Any, self.model)
        return model.encode([text], convert_to_numpy=True)[0]
