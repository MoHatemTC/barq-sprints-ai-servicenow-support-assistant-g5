"""Hybrid Retriever module implementing Dense + Sparse search with Reciprocal Rank Fusion (RRF).

Combines:
1. Dense Vector Search (cosine similarity using Qdrant vector index).
2. Sparse Keyword Search (BM25 Okapi algorithm over document payload text).
3. Reciprocal Rank Fusion (RRF) algorithm to produce optimal fused rankings.
"""

import math
import re
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from qdrant_client.models import FieldCondition, Filter, MatchAny

logger = logging.getLogger("servicenow_support.hybrid_retriever")
from langfuse import observe

# Tokenizer helper supporting English & Arabic
TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> List[str]:
    """Lowercase tokenization supporting multilingual text (English, Arabic, etc.)."""
    if not text:
        return []
    return [t.lower() for t in TOKEN_RE.findall(text)]


class BM25SparseSearch:
    """Okapi BM25 keyword search implementation for sparse ranking."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b

    def score(self, query: str, documents: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], float]]:
        """Score candidate document payload dicts using Okapi BM25.
        
        Each dict in documents must contain a 'content' or 'text' field.
        """
        if not query or not documents:
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return [(doc, 0.0) for doc in documents]

        N = len(documents)
        doc_tokens_list: List[List[str]] = []
        doc_lens: List[int] = []

        for doc in documents:
            text = doc.get("content") or doc.get("text") or doc.get("title") or ""
            tokens = tokenize(text)
            doc_tokens_list.append(tokens)
            doc_lens.append(len(tokens))

        avgdl = sum(doc_lens) / N if N > 0 else 1.0
        if avgdl == 0:
            avgdl = 1.0

        # Document frequency (df) calculation
        df: Dict[str, int] = {}
        for tokens in doc_tokens_list:
            unique_tokens = set(tokens)
            for token in unique_tokens:
                df[token] = df.get(token, 0) + 1

        # Inverse Document Frequency (IDF) calculation with smoothing
        idf: Dict[str, float] = {}
        for token in query_tokens:
            n_t = df.get(token, 0)
            idf[token] = math.log(1.0 + (N - n_t + 0.5) / (n_t + 0.5))

        # Calculate BM25 score for each document
        scored_docs = []
        for idx, doc in enumerate(documents):
            tokens = doc_tokens_list[idx]
            doc_len = doc_lens[idx]
            if doc_len == 0:
                scored_docs.append((doc, 0.0))
                continue

            # Term frequencies in document
            tf: Dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1

            score = 0.0
            for qt in query_tokens:
                if qt not in tf:
                    continue
                freq = tf[qt]
                numerator = freq * (self.k1 + 1.0)
                denominator = freq + self.k1 * (1.0 - self.b + self.b * (doc_len / avgdl))
                score += idf.get(qt, 0.0) * (numerator / denominator)

            scored_docs.append((doc, round(score, 4)))

        # Sort descending by BM25 score
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        return scored_docs


class HybridRetriever:
    """Hybrid Retriever fusing Dense vector search and BM25 Sparse search using RRF."""

    def __init__(
        self,
        qdrant_service: Any,
        embedder: Any,
        top_k: int = 5,
        dense_candidate_k: Optional[int] = None,
        sparse_candidate_k: Optional[int] = None,
        rrf_k: int = 60,
        allowed_states: tuple = ("published",),
    ):
        self.qdrant_service = qdrant_service
        self.embedder = embedder
        self.top_k = top_k
        self.dense_candidate_k = dense_candidate_k if dense_candidate_k is not None else top_k
        self.sparse_candidate_k = sparse_candidate_k if sparse_candidate_k is not None else top_k
        self.rrf_k = rrf_k
        self.allowed_states = allowed_states
        self.bm25_search = BM25SparseSearch()

    def _get_qdrant_client_and_collection(self) -> Tuple[Any, str]:
        client = getattr(self.qdrant_service, "client", self.qdrant_service)
        collection_name = getattr(self.qdrant_service, "collection_name", "kb_collection")
        return client, collection_name

    def _build_filter(self) -> Filter:
        return Filter(
            must=[
                FieldCondition(
                    key="workflow_state",
                    match=MatchAny(any=list(self.allowed_states)),
                )
            ]
        )

    def dense_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Perform Dense vector similarity search against Qdrant."""
        client, collection_name = self._get_qdrant_client_and_collection()
        vector = self.embedder.embed_text(query)
        state_filter = self._build_filter()

        response = client.query_points(
            collection_name=collection_name,
            query=vector,
            query_filter=state_filter,
            limit=limit,
            with_payload=True,
        )

        hits: List[Dict[str, Any]] = []
        for point in getattr(response, "points", []):
            payload = point.payload or {}
            point_id = str(getattr(point, "id", None) or f"{payload.get('article_id')}_{payload.get('chunk_index', 0)}")
            hits.append({
                "id": point_id,
                "article_id": payload.get("article_id") or payload.get("number"),
                "title": payload.get("title") or payload.get("short_description") or "",
                "content": payload.get("text") or payload.get("content") or "",
                "chunk_index": payload.get("chunk_index", 0),
                "workflow_state": payload.get("workflow_state") or "published",
                "page_start": payload.get("page_start"),
                "page_end": payload.get("page_end"),
                "heading_path": payload.get("heading_path", []),
                "section_ids": payload.get("section_ids", []),
                "content_types": payload.get("content_types", []),
                "dense_score": round(float(getattr(point, "score", 0.0) or 0.0), 4),
            })
        return hits

    def sparse_search(self, query: str, candidate_pool: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        """Perform BM25 Sparse search across candidate document pool."""
        scored_pairs = self.bm25_search.score(query, candidate_pool)
        results = []
        for doc, score in scored_pairs[:limit]:
            doc_copy = dict(doc)
            doc_copy["sparse_score"] = score
            results.append(doc_copy)
        return results

    def _fetch_all_candidates_for_sparse(self) -> List[Dict[str, Any]]:
        """Scroll candidate pool from Qdrant for sparse indexing."""
        client, collection_name = self._get_qdrant_client_and_collection()
        state_filter = self._build_filter()
        if not hasattr(client, "scroll"):
            return []
        try:
            scroll_res, _ = client.scroll(
                collection_name=collection_name,
                scroll_filter=state_filter,
                limit=100,
                with_payload=True,
                with_vectors=False,
            )
            pool = []
            for point in scroll_res:
                payload = point.payload or {}
                point_id = str(getattr(point, "id", None) or f"{payload.get('article_id')}_{payload.get('chunk_index', 0)}")
                pool.append({
                    "id": point_id,
                    "article_id": payload.get("article_id") or payload.get("number"),
                    "title": payload.get("title") or payload.get("short_description") or "",
                    "content": payload.get("text") or payload.get("content") or "",
                    "chunk_index": payload.get("chunk_index", 0),
                    "workflow_state": payload.get("workflow_state") or "published",
                    "page_start": payload.get("page_start"),
                    "page_end": payload.get("page_end"),
                    "heading_path": payload.get("heading_path", []),
                    "section_ids": payload.get("section_ids", []),
                    "content_types": payload.get("content_types", []),
                })
            return pool
        except Exception as exc:
            logger.warning(f"Could not fetch full sparse pool from Qdrant: {exc}")
            return []

    def reciprocal_rank_fusion(
        self,
        dense_hits: List[Dict[str, Any]],
        sparse_hits: List[Dict[str, Any]],
        weights: Tuple[float, float] = (1.0, 1.0),
    ) -> List[Dict[str, Any]]:
        """Combine dense and sparse search results using Reciprocal Rank Fusion (RRF).
        
        RRF_score = w_dense / (k + rank_dense) + w_sparse / (k + rank_sparse)
        """
        w_dense, w_sparse = weights
        doc_map: Dict[str, Dict[str, Any]] = {}
        rrf_scores: Dict[str, float] = {}

        def get_doc_key(doc: Dict[str, Any]) -> str:
            return doc.get("id") or f"{doc.get('article_id')}_{doc.get('chunk_index')}"

        # Process Dense Ranks
        for rank, hit in enumerate(dense_hits, start=1):
            key = get_doc_key(hit)
            if key not in doc_map:
                doc_map[key] = dict(hit)
            doc_map[key]["dense_rank"] = rank
            doc_map[key]["dense_score"] = hit.get("dense_score", 0.0)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (w_dense / (self.rrf_k + rank))

        # Process Sparse Ranks
        for rank, hit in enumerate(sparse_hits, start=1):
            key = get_doc_key(hit)
            if key not in doc_map:
                doc_map[key] = dict(hit)
            else:
                # Merge payload attributes
                doc_map[key].update({k: v for k, v in hit.items() if k not in doc_map[key]})
            doc_map[key]["sparse_rank"] = rank
            doc_map[key]["sparse_score"] = hit.get("sparse_score", 0.0)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (w_sparse / (self.rrf_k + rank))

        # Compile final list sorted by RRF score
        fused_hits: List[Dict[str, Any]] = []
        for key, rrf_score in sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True):
            doc = doc_map[key]
            doc["rrf_score"] = round(rrf_score, 6)
            # Use dense_score if available (even 0.0), otherwise fallback to normalized rrf_score
            dense_sc = doc.get("dense_score")
            doc["score"] = dense_sc if dense_sc is not None else round(rrf_score * 30, 4)
            fused_hits.append(doc)

        return fused_hits

    @observe(as_type="retriever", name="hybrid-retriever")
    def search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """Execute Hybrid Search (Dense + Sparse) with Reciprocal Rank Fusion."""
        k = top_k or self.top_k
        if not query or not query.strip():
            return []

        cleaned_query = query.strip()

        # 1. Execute Dense Search
        dense_hits = self.dense_search(cleaned_query, limit=self.dense_candidate_k)

        # 2. Build Candidate Pool for Sparse Search
        candidate_pool = list(dense_hits)
        additional_pool = self._fetch_all_candidates_for_sparse()

        # Merge candidate pools without duplicates
        seen_keys: Set[str] = {h.get("id") or f"{h.get('article_id')}_{h.get('chunk_index')}" for h in candidate_pool}
        for item in additional_pool:
            key = item.get("id") or f"{item.get('article_id')}_{item.get('chunk_index')}"
            if key not in seen_keys:
                candidate_pool.append(item)
                seen_keys.add(key)

        # 3. Execute BM25 Sparse Search
        sparse_hits = self.sparse_search(cleaned_query, candidate_pool, limit=self.sparse_candidate_k)

        # 4. Perform Reciprocal Rank Fusion (RRF)
        fused_hits = self.reciprocal_rank_fusion(dense_hits, sparse_hits)

        return fused_hits[:k]
