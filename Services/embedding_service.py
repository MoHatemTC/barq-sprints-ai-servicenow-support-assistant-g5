import os

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer


load_dotenv()

DEFAULT_MODEL_NAME = "BAAI/bge-base-en-v1.5"


class EmbeddingService:

    def __init__(self, model_name: str | None = None):
        self.model = SentenceTransformer(
            model_name or os.getenv(
                "EMBEDDING_MODEL_NAME",
                DEFAULT_MODEL_NAME
            )
        )

    def embed_text(self, text: str) -> list[float]:
        if not text:
            return []

        vector = self.model.encode(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True
        )

        return vector.tolist()

    def embed_chunks(self, chunks: list[str]) -> list[list[float]]:
        if not chunks:
            return []

        vectors = self.model.encode(
            chunks,
            normalize_embeddings=True,
            convert_to_numpy=True
        )

        return vectors.tolist()