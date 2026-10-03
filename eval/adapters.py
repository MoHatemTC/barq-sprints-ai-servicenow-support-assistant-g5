"""System adapter: one interface, two implementations.

    LiveAdapter      -> real Qdrant + embedding model + ReAct agent + LLM
    SnapshotAdapter  -> replays results recorded earlier (fully offline)

The evaluation code only ever talks to RagAdapter, so it never needs to know
which one it is using. Project imports (Qdrant, agent, LLM) are done lazily
inside LiveAdapter, so snapshot mode works on a machine with no live stack.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from eval.dataset import make_query

DEFAULT_SNAPSHOT = Path("eval/fixtures/rag_snapshot.json")


# --------------------------------------------------------------------------- #
# Data shapes
# --------------------------------------------------------------------------- #
@dataclass
class RetrievedChunk:
    text: str
    doc_id: str          # KB number, e.g. "KB0010174"
    section: str         # heading path, or "chunk_<n>" when the chunk has no headings
    score: float
    title: str = ""
    chunk_index: int | None = None


@dataclass
class AnswerResult:
    text: str                                   # numbered procedure, "" when escalated
    outcome: str                                # "suggested" | "escalated"
    sources: list[str] = field(default_factory=list)
    retrieved_chunks: list[RetrievedChunk] = field(default_factory=list)  # chunks the agent actually used
    max_score: float = 0.0
    reason: str | None = None

    @property
    def answered(self) -> bool:
        return self.outcome == "suggested" and bool(self.text.strip())


def chunk_from_hit(hit: dict[str, Any]) -> RetrievedChunk:
    """Convert a retriever/agent chunk dict into a RetrievedChunk."""
    heading = hit.get("heading_path") or []
    idx = hit.get("chunk_index")
    section = " > ".join(heading) if heading else f"chunk_{idx if idx is not None else 0}"
    return RetrievedChunk(
        text=hit.get("content") or hit.get("text") or "",
        doc_id=str(hit.get("article_id") or ""),
        section=section,
        score=float(hit.get("score") or 0.0),
        title=hit.get("title") or "",
        chunk_index=idx,
    )


# --------------------------------------------------------------------------- #
# Interface
# --------------------------------------------------------------------------- #
class RagAdapter(ABC):
    @abstractmethod
    def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        """Top-k chunks BEFORE any score threshold, best first."""

    @abstractmethod
    def generate_answer(self, short_description: str, description: str = "") -> AnswerResult:
        """Run the full pipeline for one incident and return the suggested answer or escalation."""

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        """Metadata about what is being evaluated (shown in the report)."""


# --------------------------------------------------------------------------- #
# Live implementation
# --------------------------------------------------------------------------- #
class LiveAdapter(RagAdapter):
    """Uses the project's own retriever and ReAct agent, so we measure the real system.

    Writes are impossible: the agent runs with FakeWriteBackPort (same as
    scripts/try_agent.py), so nothing is ever sent to ServiceNow.
    """

    def __init__(self) -> None:
        from dotenv import load_dotenv

        load_dotenv()
        self._retriever = None

    def _get_retriever(self):
        if self._retriever is None:
            from agent.agent import KnowledgeRetriever

            # minimum_score=-1 keeps every hit; the production threshold is
            # evaluated separately (see best score vs SCORE_THRESHOLD in the report).
            self._retriever = KnowledgeRetriever(minimum_score=-1.0)
        return self._retriever

    def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        retriever = self._get_retriever()
        retriever.top_k = top_k
        result = retriever.retrieve(query)   # raises on Qdrant/model errors: failures must be loud
        return [chunk_from_hit(h) for h in result["chunks"]]

    def generate_answer(self, short_description: str, description: str = "") -> AnswerResult:
        from agent.ports import FakeWriteBackPort
        from Services.incident_preparer import IncidentContextPreparer
        from src.agent.factory import build_agent_tools, new_run_context
        from src.agent.react_agent import run_agent

        incident = IncidentContextPreparer().process_payload(
            "0" * 32, "INC0000000", short_description, description
        )
        if not incident.is_safe:  # same guardrail as the webhook
            return AnswerResult(text="", outcome="escalated", reason="incident flagged as unsafe")

        ctx = new_run_context(incident.sys_id, incident.original_number)
        tools = build_agent_tools(ctx, write_back_port=FakeWriteBackPort())
        result = run_agent(incident.sys_id, incident, tools, ctx=ctx)

        suggested = result.outcome == "suggested" and bool(result.procedure)
        return AnswerResult(
            text=result.procedure if suggested else "",
            outcome="suggested" if suggested else "escalated",
            sources=list(result.sources or []),
            retrieved_chunks=[chunk_from_hit(h) for h in (result.retrieved_chunks or [])],
            max_score=float(result.max_score or 0.0),
            reason=None if suggested else (result.reason or result.fallback_reason),
        )

    def describe(self) -> dict[str, Any]:
        import os

        return {
            "mode": "live",
            "embedding_model": os.getenv("EMBEDDING_MODEL_NAME"),
            "llm_model": os.getenv("LLM_MODEL"),
            "score_threshold": os.getenv("SCORE_THRESHOLD", "0.70"),
        }


# --------------------------------------------------------------------------- #
# Snapshot implementation
# --------------------------------------------------------------------------- #
class SnapshotMiss(KeyError):
    """The snapshot has no recording for this query. Never silently fall back."""


class SnapshotAdapter(RagAdapter):
    def __init__(self, path: str | Path = DEFAULT_SNAPSHOT) -> None:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.meta: dict[str, Any] = data["meta"]
        self._entries: dict[str, dict[str, Any]] = {e["query"]: e for e in data["entries"]}
        self.path = str(path)

    def _entry(self, query: str) -> dict[str, Any]:
        try:
            return self._entries[query]
        except KeyError:
            raise SnapshotMiss(
                f"No recording for this query in {self.path}. The dataset probably changed: "
                f"re-run `uv run python -m eval.record_snapshot`. Query starts with: {query[:70]!r}"
            ) from None

    def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        recorded_k = int(self.meta.get("top_k", 0))
        if top_k > recorded_k:
            raise ValueError(f"Snapshot only holds top_k={recorded_k}; asked for {top_k}. Re-record.")
        return [RetrievedChunk(**c) for c in self._entry(query)["retrieval"][:top_k]]

    def generate_answer(self, short_description: str, description: str = "") -> AnswerResult:
        a = self._entry(make_query(short_description, description))["answer"]
        return AnswerResult(
            text=a["text"],
            outcome=a["outcome"],
            sources=a.get("sources", []),
            retrieved_chunks=[RetrievedChunk(**c) for c in a.get("retrieved_chunks", [])],
            max_score=a.get("max_score", 0.0),
            reason=a.get("reason"),
        )

    def describe(self) -> dict[str, Any]:
        return {"mode": "snapshot", "file": self.path, **self.meta}


def result_to_dict(result: AnswerResult) -> dict[str, Any]:
    return asdict(result)