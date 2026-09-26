import os

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

DEFAULT_MODEL_NAME = "BAAI/bge-base-en-v1.5"
# Single source of truth: qdrant_service imports this to build the collection name.
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME") or DEFAULT_MODEL_NAME


class EmbeddingService:

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or EMBEDDING_MODEL_NAME
        self.model = SentenceTransformer(self.model_name)

    def embed_text(self, text: str) -> list[float]:
        if not text:
            return []
        vector = self.model.encode(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return vector.tolist()

    def embed_chunks(self, chunks: list[str]) -> list[list[float]]:
        if not chunks:
            return []
        vectors = self.model.encode(
            chunks,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return vectors.tolist()
