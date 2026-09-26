"""Per-run state for the ReAct agent (S3.4).

One incident = one RunContext. The loop and the tools both write here, so the
grounding gate can check "was this article actually retrieved?" and the trace
can show everything that happened.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievedArticle:
    article_id: str
    title: str
    best_score: float
    chunks: list[dict] = field(default_factory=list)


@dataclass
class RunContext:
    sys_id: str
    incident_number: str

    # retrieval state (filled by searchKB)
    retrieved: dict[str, RetrievedArticle] = field(default_factory=dict)
    search_queries: list[str] = field(default_factory=list)
    max_score: float = 0.0
    any_relevant: bool = False

    # outcome state (filled by terminal tools)
    finished: bool = False
    outcome: str | None = None          # "suggested" | "escalated"
    final_payload: dict[str, Any] = field(default_factory=dict)
    work_notes: list[str] = field(default_factory=list)

    # step-by-step log for the evidence transcript
    events: list[dict[str, Any]] = field(default_factory=list)

    def record_search(self, query: str, relevant_chunks: list[dict], best: float | None) -> None:
        self.search_queries.append(query)
        if best is not None:
            self.max_score = max(self.max_score, float(best))
        for c in relevant_chunks:
            aid = str(c.get("article_id"))
            art = self.retrieved.get(aid)
            if art is None:
                art = RetrievedArticle(aid, str(c.get("title") or ""), float(c.get("score") or 0.0))
                self.retrieved[aid] = art
            art.best_score = max(art.best_score, float(c.get("score") or 0.0))
            art.chunks.append(c)
        if relevant_chunks:
            self.any_relevant = True

    def all_chunks(self) -> list[dict]:
        """Unique chunks, best score first (same chunk can come back from 2 searches)."""
        unique: dict[tuple, dict] = {}
        for art in self.retrieved.values():
            for c in art.chunks:
                key = (c.get("article_id"), c.get("chunk_index"), str(c.get("content", ""))[:80])
                if key not in unique or c.get("score", 0) > unique[key].get("score", 0):
                    unique[key] = c
        return sorted(unique.values(), key=lambda c: c.get("score", 0), reverse=True)

    def log(self, kind: str, **data: Any) -> None:
        self.events.append({"step": len(self.events) + 1, "kind": kind, **data})
