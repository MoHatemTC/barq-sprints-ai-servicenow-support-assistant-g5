import importlib.util
import threading
from pathlib import Path
import sys
from types import SimpleNamespace

from Services.embedding_service import DEFAULT_MODEL_NAME
from Services.qdrant_service import COLLECTION_NAME, QdrantService, VECTOR_SIZE


ROOT = Path(__file__).resolve().parents[1]
CHUNKING_PATH = ROOT / "chunking and indexing" / "chunking.py"
SPEC = importlib.util.spec_from_file_location("document_chunking", CHUNKING_PATH)
chunking = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = chunking
SPEC.loader.exec_module(chunking)


def test_default_embedding_model_matches_qdrant_collection_dimensions():
    assert DEFAULT_MODEL_NAME == "BAAI/bge-m3"
    assert VECTOR_SIZE == 1024
    assert COLLECTION_NAME.endswith("_baai_bge_m3")


def test_semantic_chunking_splits_on_low_adjacent_similarity(tmp_path):
    document = tmp_path / "document.md"
    document.write_text(
        "Router configuration is managed in the network console. "
        "Open the network console and select the router. "
        "Database backups run every evening. "
        "Restore the database from the latest backup.",
        encoding="utf-8",
    )

    def encode(sentences):
        return [
            [1.0, 0.0],
            [0.9, 0.1],
            [0.0, 1.0],
            [0.1, 0.9],
        ]

    chunks = chunking.build_chunks(
        document,
        target_words=400,
        overlap_words=0,
        semantic_threshold=0.5,
        sentence_encoder=encode,
    )

    assert len(chunks) == 2
    assert chunks[0]["text"].endswith("select the router.")
    assert chunks[1]["text"].startswith("Database backups")


class FakeScrollClient:
    def __init__(self, points):
        self.points = points

    def scroll(self, **kwargs):
        assert kwargs["with_payload"] is True
        assert kwargs["with_vectors"] is False
        return self.points, None


def test_bm25_search_returns_lexically_relevant_chunks():
    matching = SimpleNamespace(
        id="match",
        payload={
            "text": "KB-11 duplicate webhook events are ignored",
            "workflow_state": "published",
        },
    )
    unrelated = SimpleNamespace(
        id="unrelated",
        payload={
            "text": "Reset the user's password in the identity portal",
            "workflow_state": "published",
        },
    )
    qdrant = object.__new__(QdrantService)
    qdrant.collection_name = "test"
    qdrant.client = FakeScrollClient([matching, unrelated])
    qdrant._bm25_cache = None
    qdrant._bm25_lock = threading.RLock()

    results = qdrant.search_bm25("KB-11 duplicate webhook", ("published",), 5)

    assert results[0][0].id == "match"
    assert results[0][1] > 0
    assert len(results) == 1
