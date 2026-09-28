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
                "scores": [],
                "all_scores": [],
                "threshold": self.score_threshold,
                "score_threshold": self.score_threshold,
                "threshold_met": False,
                "threshold_passed": False,
                "human_review_required": True,
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
            passed_scores = [h["score"] for h in passed_chunks]
            all_scores = [h["score"] for h in hits]
            avg_score = round(sum(all_scores) / len(all_scores), 4) if all_scores else 0.0
            threshold_met = bool(passed_chunks)
            human_review_required = not threshold_met

            # 4. Record retrieval ledger in RunContext
            self.run_context.record_retrieval(
                query=cleaned_query,
                chunks=passed_chunks,
                best_score=best_score,
            )

            # 5. Return structured observation schema with metrics & threshold flags
            observation: Dict[str, Any] = {
                "query": cleaned_query,
                "count": len(passed_chunks),
                "total_candidates": len(hits),
                # Relevance scoring metrics
                "best_score": best_score,
                "avg_score": avg_score,
                "scores": passed_scores,
                "all_scores": [(h["article_id"], h["score"]) for h in hits],
                # Threshold flags
                "threshold": self.score_threshold,
                "score_threshold": self.score_threshold,
                "threshold_met": threshold_met,
                "threshold_passed": threshold_met,
                "human_review_required": human_review_required,
                "chunks": passed_chunks,
            }

            if not passed_chunks:
                observation["status"] = "no_results"
                observation["message"] = (
                    f"No knowledge article scored above threshold {self.score_threshold} "
                    f"(best: {best_score})."
                )
            else:
                observation["status"] = "success"

            return observation

        except Exception as exc:
            logger.exception("searchKB execution error")
            return {
                "status": "error",
                "query": cleaned_query,
                "error": f"Search failed: {type(exc).__name__}: {str(exc)}",
                "chunks": [],
                "count": 0,
                "best_score": 0.0,
                "scores": [],
                "all_scores": [],
                "threshold": self.score_threshold,
                "score_threshold": self.score_threshold,
                "threshold_met": False,
                "threshold_passed": False,
                "human_review_required": True,
            }
