"""Task 5: filtered KB retrieval and a read-only LangChain agent.

Uses the shared EmbeddingService and QdrantService so ingestion and
retrieval always use the same model and the same collection.
"""

import logging
import os
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

    def retrieve(self, query: str) -> dict[str, Any]:
        """Full result: chunks above threshold + scores for tracing/confidence."""
        if not query or not query.strip():
            return self._result(query, [], [], reason="empty query")

        vector = self.embedder.embed_text(query.strip())

        # No score_threshold here on purpose: we want the best score
        # even when it is below threshold (FR-17 confidence, demo, traces).
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

        hits = []
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

        chunks = [h for h in hits if h["score"] >= self.minimum_score]
        reason = None if chunks else "no chunk above threshold"
        return self._result(query, hits, chunks, reason)

    def search(self, query: str) -> list[dict[str, Any]]:
        """Backward-compatible: chunks above threshold only."""
        return self.retrieve(query)["chunks"]

    def _result(self, query, hits, chunks, reason=None) -> dict[str, Any]:
        best_score = max((h["score"] for h in hits), default=None)
        result = {
            "query": query,
            "chunks": chunks,                          # empty when below threshold
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


def create_read_only_agent():
    """Build the agent with read-only tools only."""
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.prompts import ChatPromptTemplate
    from Services.llm import get_llm

    assert_read_only(READ_ONLY_TOOLS)

    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Use search_knowledge to answer using only published KB chunks. "
                "This agent is read-only. If search_knowledge returns "
                "human_review_required=true or no chunks, reply NO_ANSWER.",
            ),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )
    agent = create_tool_calling_agent(llm, READ_ONLY_TOOLS, prompt)
    return AgentExecutor(agent=agent, tools=READ_ONLY_TOOLS, verbose=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    chunks, articles = count_kb_articles()
    print(f"Collection: {get_knowledge_retriever().qdrant.collection_name}")
    print(f"Vector chunks: {chunks} | Unique articles: {articles}")

    for q in ("wifi keeps disconnecting on my laptop", "how do I bake sourdough bread"):
        r = search_knowledge.invoke({"query": q})
        print(f"\n{q!r}\n  best={r['best_score']} review={r['human_review_required']} "
              f"returned={len(r['chunks'])} scores={r.get('all_scores')}")