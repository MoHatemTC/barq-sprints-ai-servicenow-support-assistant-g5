"""One instance per process of the heavy objects.

The bge model (~400 MB) and the Qdrant client are created once and reused by
KB ingestion, KB events and incident retrieval. Thread-safe because the
pipeline runs inside asyncio.to_thread workers.
"""

import threading

from Services.embedding_service import EmbeddingService
from Services.qdrant_service import QdrantService

_lock = threading.RLock()
_embedder: EmbeddingService | None = None
_qdrant: QdrantService | None = None
_ingestion = None


def get_embedder() -> EmbeddingService:
    global _embedder
    if _embedder is None:
        with _lock:
            if _embedder is None:
                _embedder = EmbeddingService()
    return _embedder


def get_qdrant() -> QdrantService:
    global _qdrant
    if _qdrant is None:
        with _lock:
            if _qdrant is None:
                _qdrant = QdrantService()
    return _qdrant


def get_ingestion_service():
    global _ingestion
    if _ingestion is None:
        with _lock:
            if _ingestion is None:
                from Services.KB_ingestion_service import KBIngestionService
                _ingestion = KBIngestionService()
    return _ingestion
