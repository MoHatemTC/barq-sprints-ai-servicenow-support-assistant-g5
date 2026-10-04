"""Unit tests for Hybrid Chunking and Hybrid Retrieval with Reciprocal Rank Fusion (RRF)."""

import pytest
from Services.chunking_service import ChunkingService, HybridChunker
from Services.hybrid_retriever import BM25SparseSearch, HybridRetriever


def test_hybrid_chunking_with_structural_headers():
    text = """# Section 1: Overview
This is the overview paragraph explaining the system.

## Subsection 1.1: Details
Here are the details for subsection 1.1.
- Step 1: Open dashboard
- Step 2: Configure settings
"""
    chunker = HybridChunker(chunk_size=50, chunk_overlap=1)
    chunks = chunker.chunk_document(text)

    assert len(chunks) >= 2
    assert chunks[0]["strategy"] == "structural"
    assert "Overview" in chunks[0]["heading_path"] or "Section 1: Overview" in chunks[0]["heading_path"]


def test_hybrid_chunking_fallback_meaning_when_no_headers():
    text = (
        "ServiceNow incident management allows IT support teams to track issues. "
        "When an incident is submitted, it is assigned a priority based on impact and urgency. "
        "The support agent can add worknotes or request additional information from HR. "
        "Once resolved, the incident status is updated to closed."
    )
    chunker = ChunkingService(chunk_size=15, chunk_overlap=1)
    chunks = chunker.chunk_text(text)

    assert len(chunks) > 1
    # Check that plain text chunking returns list of non-empty strings
    assert all(isinstance(c, str) and len(c) > 0 for c in chunks)


def test_bm25_sparse_search():
    bm25 = BM25SparseSearch()
    docs = [
        {"id": "doc1", "text": "Annual leave request approval procedure and policy"},
        {"id": "doc2", "text": "VPN connectivity issues and network troubleshooting"},
        {"id": "doc3", "text": "Password reset procedure for single sign on"},
    ]

    scored = bm25.score("annual leave approval", docs)
    assert len(scored) == 3
    # Top result should be doc1
    assert scored[0][0]["id"] == "doc1"
    assert scored[0][1] > 0.0


def test_reciprocal_rank_fusion():
    dense_hits = [
        {"id": "doc1", "article_id": "KB001", "chunk_index": 0, "dense_score": 0.88},
        {"id": "doc2", "article_id": "KB002", "chunk_index": 0, "dense_score": 0.82},
    ]
    sparse_hits = [
        {"id": "doc2", "article_id": "KB002", "chunk_index": 0, "sparse_score": 4.5},
        {"id": "doc3", "article_id": "KB003", "chunk_index": 0, "sparse_score": 3.1},
    ]

    class FakeEmbedder:
        def embed_text(self, text):
            return [0.1, 0.2]

    class FakeQdrant:
        collection_name = "test"

    retriever = HybridRetriever(qdrant_service=FakeQdrant(), embedder=FakeEmbedder(), rrf_k=60)
    fused = retriever.reciprocal_rank_fusion(dense_hits, sparse_hits)

    assert len(fused) == 3
    # Check RRF scores are calculated
    assert "rrf_score" in fused[0]
    assert fused[0]["rrf_score"] > 0
