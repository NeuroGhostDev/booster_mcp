from sentence_transformers import SentenceTransformer

class Embedder:
    def __init__(self):
        # Оптимальная модель для базового семантического поиска
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def embed(self, text):
        return self.model.encode([text])[0]
