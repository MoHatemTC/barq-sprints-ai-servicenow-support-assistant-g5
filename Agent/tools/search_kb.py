"""searchKB tool implementation for Sprint 3.3.

Non-terminal tool executing dense vector search against Qdrant using the configured
embedding model and collection, filtering to published articles, enforcing score threshold,
recording retrieval state in RunContext, and returning structured observation schemas.
"""

import logging
from typing import Any, Callable, Dict, List, Optional
from qdrant_client.models import FieldCondition, Filter, MatchAny

from agent.config import ALLOWED_WORKFLOW_STATES, SCORE_THRESHOLD, TOP_K
from agent.run_context import RunContext

logger = logging.getLogger("agent.tools.search_kb")


class SearchKBTool:
    """Tool class implementing the searchKB operation bound to RunContext."""

    def __init__(
        self,
        run_context: RunContext,
        qdrant_service: Any,
        embedder: Any,
        score_threshold: float = SCORE_THRESHOLD,
        top_k: int = TOP_K,
        allowed_states: tuple = ALLOWED_WORKFLOW_STATES,
    ):
        self.run_context = run_context
        self.qdrant_service = qdrant_service
        self.embedder = embedder
        self.score_threshold = score_threshold
        self.top_k = top_k
        self.allowed_states = allowed_states

    def __call__(self, query: str) -> Dict[str, Any]:
        return self.run(query)

    def run(self, query: str) -> Dict[str, Any]:
        """Execute searchKB against Qdrant."""
        # 1. State check: Enforce terminal semantics
        finish_check = self.run_context.check_finished()
        if finish_check:
            return finish_check

        # 2. Input validation
        if not query or not query.strip():
            return {
                "status": "error",
                "error": "Query cannot be empty.",
                "chunks": [],
                "count": 0,
                "best_score": 0.0,
            }

        cleaned_query = query.strip()

        # 3. Dense search execution with clean error handling
        try:
            # Generate query embedding
            vector = self.embedder.embed_text(cleaned_query)

            # Query Qdrant with published-only filter
            # Support both 'workflow_state' and 'status' payload attributes
            state_filter = Filter(
                should=[
                    FieldCondition(
                        key="workflow_state",
                        match=MatchAny(any=list(self.allowed_states)),
                    ),
                    FieldCondition(
                        key="status",
                        match=MatchAny(any=list(self.allowed_states)),
                    ),
                ]
            )

            client = getattr(self.qdrant_service, "client", self.qdrant_service)
            collection_name = getattr(self.qdrant_service, "collection_name", "kb_collection")

            response = client.query_points(
                collection_name=collection_name,
                query=vector,
                query_filter=state_filter,
                limit=self.top_k,
                with_payload=True,
            )

            hits: List[Dict[str, Any]] = []
            for point in getattr(response, "points", []):
                payload = point.payload or {}
                hits.append({
                    "article_id": payload.get("article_id") or payload.get("number"),
                    "title": payload.get("title") or payload.get("short_description") or "",
                    "content": payload.get("text") or payload.get("content") or "",
                    "chunk_index": payload.get("chunk_index", 0),
                    "workflow_state": payload.get("workflow_state") or payload.get("status") or "published",
                    "score": round(float(point.score or 0.0), 4),
                })

            best_score = max((h["score"] for h in hits), default=0.0)
            passed_chunks = [h for h in hits if h["score"] >= self.score_threshold]

            # 4. Record retrieval ledger in RunContext
            self.run_context.record_retrieval(
                query=cleaned_query,
                chunks=passed_chunks,
                best_score=best_score,
            )

            # 5. Return structured observation schema
            if not passed_chunks:
                return {
                    "status": "no_results",
                    "query": cleaned_query,
                    "count": 0,
                    "best_score": best_score,
                    "threshold": self.score_threshold,
                    "message": f"No knowledge article scored above threshold {self.score_threshold} (best: {best_score}).",
                    "chunks": [],
                }

            return {
                "status": "success",
                "query": cleaned_query,
                "count": len(passed_chunks),
                "best_score": best_score,
                "threshold": self.score_threshold,
                "chunks": passed_chunks,
            }

        except Exception as exc:
            logger.exception("searchKB execution error")
            return {
                "status": "error",
                "query": cleaned_query,
                "error": f"Search failed: {type(exc).__name__}: {str(exc)}",
                "chunks": [],
                "count": 0,
                "best_score": 0.0,
            }
