from sentence_transformers import SentenceTransformer


class EmbeddingService:

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)

    def embed_text(self, text: str) -> list[float]:
        if not text:
            return []

        vector = self.model.encode(
            text,
            convert_to_numpy=True
        )

        return vector.tolist()

    def embed_chunks(self, chunks: list[str]) -> list[list[float]]:
        if not chunks:
            return []

        vectors = self.model.encode(
            chunks,
            convert_to_numpy=True
        )

        return vectors.tolist()