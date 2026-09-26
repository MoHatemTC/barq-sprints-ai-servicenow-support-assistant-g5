import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Agent.agent import KnowledgeRetriever


class FakeEmbedder:
    def embed_text(self, query: str) -> list[float]:
        assert query == "duplicate webhook event"
        return [0.1, 0.2]


class FakeQdrantClient:
    def query_points(self, **kwargs):
        assert kwargs["limit"] == 5
        assert kwargs["with_payload"] is True
        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    score=0.91,
                    payload={
                        "article_id": "doc_001",
                        "title": "AI ServiceNow IT Incident Resolution Assistant Knowledge Base",
                        "text": "A duplicate event returns 202 Accepted and is not dispatched.",
                        "chunk_index": 12,
                        "workflow_state": "published",
                        "document_id": "doc_001",
                        "source_file": "document.md",
                        "page_start": 16,
                        "page_end": 16,
                        "heading_path": ["Part 3 · The event contract", "The webhook contract KB-11"],
                        "section_ids": ["KB-11"],
                        "content_types": ["prose", "table"],
                    },
                )
            ]
        )


class FakeQdrant:
    collection_name = "test_collection"

    def __init__(self):
        self.client = FakeQdrantClient()


def test_document_retrieval_preserves_provenance_metadata():
    retriever = KnowledgeRetriever(
        qdrant=FakeQdrant(),
        embedder=FakeEmbedder(),
        minimum_score=0.70,
        top_k=5,
    )

    result = retriever.retrieve("duplicate webhook event")

    assert result["human_review_required"] is False
    assert len(result["chunks"]) == 1
    hit = result["chunks"][0]
    assert hit["article_id"] == "doc_001"
    assert hit["page_start"] == 16
    assert hit["page_end"] == 16
    assert hit["section_ids"] == ["KB-11"]
    assert hit["heading_path"][-1] == "The webhook contract KB-11"
    assert hit["content_types"] == ["prose", "table"]