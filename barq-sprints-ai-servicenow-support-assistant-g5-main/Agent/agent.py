"""Task 5: filtered KB retrieval (+ read-only tool check).

The ReAct loop itself lives in src/agent/react_agent.py (S3.4).

Uses the shared EmbeddingService and QdrantService so ingestion and
retrieval always use the same model and the same collection.
"""

import logging
import os
import re
from typing import Any

from dotenv import load_dotenv
from langchain_core.tools import tool
from qdrant_client.models import FieldCondition, Filter, MatchAny

from Services.embedding_service import EmbeddingService
from Services.qdrant_service import QdrantService
from Services.shared import get_embedder, get_qdrant

load_dotenv()
logger = logging.getLogger(__name__)

SCORE_THRESHOLD = float(os.getenv("SCORE_THRESHOLD", "0.70"))
TOP_K = int(os.getenv("TOP_K", "5"))
# FR-11: published only by default
ALLOWED_WORKFLOW_STATES = tuple(
    s.strip().lower()
    for s in os.getenv("ALLOWED_WORKFLOW_STATES", "published").split(",")
    if s.strip()
)

QUERY_SYNONYMS = {
    "wifi": ["wifi", "wi-fi", "wireless", "network disconnect", "internet disconnect"],
    "printer": ["printer", "print queue", "offline printer", "scanner"],
    "password": ["password", "login", "locked out", "reset password", "credential", "sign in"],
    "vpn": ["vpn", "virtual private network", "remote access", "network drop"],
    "email": ["email", "mail", "outbox", "sync", "exchange"],
    "slow startup": ["slow startup", "startup", "boot", "performance", "laggy"],
    "shared drive": ["shared drive", "network drive", "folder access", "file access", "permissions"],
    "audio": ["microphone", "webcam", "audio", "voice", "meeting audio", "headset"],
    "hotspot": ["hotspot", "mobile tether", "network bridge", "phone internet"],
    "display": ["monitor", "display", "screen", "flicker", "external monitor"],
    "battery": ["battery", "power", "idle drain", "laptop drain"],
    "portal": ["portal", "browser", "login page", "help portal", "website"],
}


class KnowledgeRetriever:
    """Embed the query, search published chunks, apply the score threshold."""

    def __init__(
        self,
        qdrant: QdrantService | None = None,
        embedder: EmbeddingService | None = None,
        minimum_score: float = SCORE_THRESHOLD,
        top_k: int = TOP_K,
        allowed_workflow_states: tuple[str, ...] = ALLOWED_WORKFLOW_STATES,
    ) -> None:
        # Shared instances: same model + client as KB ingestion (loaded once)
        self.qdrant = qdrant or get_qdrant()
        self.embedder = embedder or get_embedder()
        self.minimum_score = minimum_score
        self.top_k = top_k
        self.allowed_workflow_states = allowed_workflow_states

    def _expanded_queries(self, query: str) -> list[str]:
        """Expand generic symptom phrasing into likely KB family keywords."""
        cleaned = re.sub(r"[^a-z0-9\s\-]+", " ", (query or "").lower())
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            return []

        variants = [cleaned]
        for canonical, terms in QUERY_SYNONYMS.items():
            if any(term in cleaned for term in terms):
                variants.append(canonical)
                variants.extend(term for term in terms if term not in cleaned)

        deduped: list[str] = []
        seen: set[str] = set()
        for variant in variants:
            variant = variant.strip()
            if not variant or variant in seen:
                continue
            deduped.append(variant)
            seen.add(variant)
        return deduped

    @staticmethod
    def _tokenize(value: str) -> set[str]:
        tokens = re.findall(r"[a-z0-9]+", (value or "").lower())
        return {token for token in tokens if len(token) > 2}

    def _lexical_boost(self, query: str, hit: dict[str, Any]) -> float:
        """Add a lexical relevance bonus for exact symptom words and KB title/body overlap."""
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return 0.0

        title = str(hit.get("title") or "")
        content = str(hit.get("content") or "")
        heading_path = " ".join(str(part) for part in (hit.get("heading_path") or []))
        section_ids = " ".join(str(part) for part in (hit.get("section_ids") or []))
        text_blob = " ".join(filter(None, [title, content, heading_path, section_ids]))
        hit_tokens = self._tokenize(text_blob)
        overlap = query_tokens & hit_tokens
        if not overlap:
            return 0.0

        coverage = len(overlap) / len(query_tokens)
        return round(0.15 + (coverage * 0.60), 4)

    def _query_points(self, query: str) -> list[dict[str, Any]]:
        vector = self.embedder.embed_text(query.strip())
        response = self.qdrant.client.query_points(
            collection_name=self.qdrant.collection_name,
            query=vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="workflow_state",
                        match=MatchAny(any=list(self.allowed_workflow_states)),
                    )
                ]
            ),
            limit=self.top_k,
            with_payload=True,
        )

        hits: list[dict[str, Any]] = []
        for point in response.points:
            payload = point.payload or {}
            hits.append(
                {
                    "article_id": payload.get("article_id"),
                    "title": payload.get("title"),
                    "content": payload.get("text") or "",
                    "chunk_index": payload.get("chunk_index"),
                    "workflow_state": payload.get("workflow_state"),
                    "document_id": payload.get("document_id"),
                    "source_file": payload.get("source_file"),
                    "page_start": payload.get("page_start"),
                    "page_end": payload.get("page_end"),
                    "heading_path": payload.get("heading_path", []),
                    "section_ids": payload.get("section_ids", []),
                    "content_types": payload.get("content_types", []),
                    "score": round(float(point.score or 0.0), 4),
                }
            )
        return hits

    def retrieve(self, query: str) -> dict[str, Any]:
        """Full result: chunks above threshold + scores for tracing/confidence."""
        if not query or not query.strip():
            return self._result(query, [], [], reason="empty query")

        hits_by_id: dict[tuple[str|None, int | None], dict[str, Any]] = {}
        for expanded_query in self._expanded_queries(query):
            for hit in self._query_points(expanded_query):
                key = (hit.get("article_id"), hit.get("chunk_index"))
                current = hits_by_id.get(key)
                if current is None or hit["score"] > current["score"]:
                    hits_by_id[key] = hit

        scored_hits: list[dict[str, Any]] = []
        for hit in hits_by_id.values():
            lexical_boost = self._lexical_boost(query, hit)
            final_score = round(min(1.0, float(hit["score"]) + lexical_boost), 4)
            hit["lexical_score"] = lexical_boost
            hit["combined_score"] = final_score
            hit["score"] = final_score
            scored_hits.append(hit)

        hits = sorted(scored_hits, key=lambda h: h["score"], reverse=True)[: self.top_k]
        chunks = [h for h in hits if h["score"] >= self.minimum_score]
        reason = None if chunks else "no chunk above threshold"
        return self._result(query, hits, chunks, reason)

    def retrieve_all(self, query: str) -> list[dict[str, Any]]:
        """Return the full unfiltered candidate set for traceability and evaluation."""
        if not query or not query.strip():
            return []

        hits_by_id: dict[tuple[str | None, int | None], dict[str, Any]] = {}
        for expanded_query in self._expanded_queries(query):
            for hit in self._query_points(expanded_query):
                key = (hit.get("article_id"), hit.get("chunk_index"))
                current = hits_by_id.get(key)
                if current is None or hit["score"] > current["score"]:
                    hits_by_id[key] = hit

        return sorted(hits_by_id.values(), key=lambda h: h["score"], reverse=True)[: self.top_k]

    def search(self, query: str) -> list[dict[str, Any]]:
        """Backward-compatible: chunks above threshold only."""
        return self.retrieve(query)["chunks"]

    def _result(self, query, hits, chunks, reason=None) -> dict[str, Any]:
        best_score = max((h["score"] for h in hits), default=None)
        result = {
            "query": query,
            "chunks": chunks,                          # empty when below threshold
            "all_hits": hits,                          # complete candidate set for tracing/eval
            "human_review_required": not chunks,       # Task 5 threshold test
            "best_score": best_score,
            "threshold": self.minimum_score,
            "all_scores": [(h["article_id"], h["score"]) for h in hits],
            "reason": reason,
        }
        logger.info(
            "KB retrieval | best=%s threshold=%s returned=%d review=%s",
            best_score, self.minimum_score, len(chunks), not chunks,
        )
        return result


_retriever: KnowledgeRetriever | None = None


def get_knowledge_retriever() -> KnowledgeRetriever:
    """Load the model and client once, on first use."""
    global _retriever
    if _retriever is None:
        _retriever = KnowledgeRetriever()
    return _retriever


def count_kb_articles() -> tuple[int, int]:
    """Return (vector chunk count, unique article count)."""
    qdrant = get_knowledge_retriever().qdrant
    article_ids: set[str] = set()
    offset = None
    while True:
        points, offset = qdrant.client.scroll(
            collection_name=qdrant.collection_name,
            offset=offset,
            limit=100,
            with_payload=["article_id"],
            with_vectors=False,
        )
        for point in points:
            article_id = (point.payload or {}).get("article_id")
            if article_id:
                article_ids.add(str(article_id))
        if offset is None:
            break
    return qdrant.count_points(), len(article_ids)


# ---------------------------------------------------------------------- #
# Agent tools (read-only)
# ---------------------------------------------------------------------- #
@tool
def search_knowledge(query: str) -> dict[str, Any]:
    """Read-only search over published ServiceNow KB chunks.
    Returns chunks above the score threshold and whether human review is required."""
    try:
        return get_knowledge_retriever().retrieve(query)
    except Exception as exc:
        # Do NOT hide errors as "no match": a wrong collection or model
        # would otherwise silently escalate every incident.
        logger.exception("KB retrieval failed")
        return {
            "query": query,
            "chunks": [],
            "human_review_required": True,
            "best_score": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


READ_ONLY_TOOLS = [search_knowledge]  # add get_incident once the Table API client is wired

FORBIDDEN_TOOL_WORDS = ("update", "write", "delete", "close", "resolve", "assign", "create", "patch")


def assert_read_only(tools) -> None:
    """Task 5 tool security check: fail fast if a write-capable tool is registered."""
    for t in tools:
        if any(word in t.name.lower() for word in FORBIDDEN_TOOL_WORDS):
            raise RuntimeError(f"Write-capable tool registered on read-only agent: {t.name}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    chunks, articles = count_kb_articles()
    print(f"Collection: {get_knowledge_retriever().qdrant.collection_name}")
    print(f"Vector chunks: {chunks} | Unique articles: {articles}")

    for q in ("wifi keeps disconnecting on my laptop", "how do I bake sourdough bread"):
        r = search_knowledge.invoke({"query": q})
        print(f"\n{q!r}\n  best={r['best_score']} review={r['human_review_required']} "
              f"returned={len(r['chunks'])} scores={r.get('all_scores')}")