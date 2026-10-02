import json
from pathlib import Path


def test_rag_dataset_has_required_coverage():
    root = Path(__file__).resolve().parents[1]
    dataset = json.loads((root / "eval" / "datasets" / "rag_golden.json").read_text(encoding="utf-8"))

    assert len(dataset) >= 20
    answerable = [row for row in dataset if row["answerable"] is True]
    unanswerable = [row for row in dataset if row["answerable"] is False]
    bilingual = [row for row in dataset if row.get("language", "en").lower() in {"ar", "ar-en", "en-ar", "bilingual"}]

    assert len(answerable) >= 15
    assert len(unanswerable) >= 3
    assert len(bilingual) >= 2

    for row in dataset:
        assert {"id", "query", "answerable", "language", "expected_article_ids", "provenance"}.issubset(row)
        assert isinstance(row["query"], str) and row["query"].strip()
        assert isinstance(row["expected_article_ids"], list)
        assert row["expected_article_ids"] or row["answerable"] is False


def test_hit_at_3_is_deterministic_and_binary():
    from eval.run_rag_eval import deterministic_hit_at_3

    expected = ["KB0010156", "KB0010161"]
    retrieved = ["KB0010156", "KB0010150", "KB0010161"]
    assert deterministic_hit_at_3(expected, retrieved) == 1.0

    retrieved2 = ["KB0010150", "KB0010153", "KB0010165"]
    assert deterministic_hit_at_3(expected, retrieved2) == 0.0


def test_answerable_expected_article_ids_exist_in_live_collection():
    import json
    from pathlib import Path

    from Services.qdrant_service import QdrantService

    root = Path(__file__).resolve().parents[1]
    dataset = json.loads((root / "eval" / "datasets" / "rag_golden.json").read_text(encoding="utf-8"))
    qdrant = QdrantService()
    points, _ = qdrant.client.scroll(
        collection_name=qdrant.collection_name,
        limit=500,
        with_payload=["article_id"],
        with_vectors=False,
    )
    live_ids = {p.payload.get("article_id") for p in points if p.payload and p.payload.get("article_id")}

    for row in dataset:
        if row.get("answerable") is True:
            missing = [aid for aid in row.get("expected_article_ids", []) if aid not in live_ids]
            assert not missing, f"{row['id']} references missing article ids: {missing}"


def test_hybrid_retrieval_prefers_keyword_match_over_weak_semantic_hit(monkeypatch):
    from types import SimpleNamespace

    from Agent.agent import KnowledgeRetriever

    class FakeEmbedder:
        def embed_text(self, text: str):
            return [0.1, 0.2, 0.3]

    class FakeQdrant:
        collection_name = "kb_test"

        class client:
            @staticmethod
            def query_points(collection_name, query, query_filter, limit, with_payload):
                return SimpleNamespace(
                    points=[
                        SimpleNamespace(
                            score=0.94,
                            payload={
                                "article_id": "KB0019999",
                                "title": "Printer offline troubleshooting",
                                "text": "The printer queue is stuck and the device shows offline.",
                                "workflow_state": "published",
                                "chunk_index": 0,
                            },
                        ),
                        SimpleNamespace(
                            score=0.90,
                            payload={
                                "article_id": "KB0018888",
                                "title": "VPN disconnect and remote access troubleshooting",
                                "text": "If the VPN keeps dropping, reconnect and verify the network connection.",
                                "workflow_state": "published",
                                "chunk_index": 1,
                            },
                        ),
                    ]
                )

    retriever = KnowledgeRetriever(qdrant=FakeQdrant(), embedder=FakeEmbedder(), minimum_score=0.50, top_k=3)
    result = retriever.retrieve("VPN keeps dropping while working from home")

    assert result["all_hits"][0]["article_id"] == "KB0018888"
    assert result["chunks"][0]["article_id"] == "KB0018888"
