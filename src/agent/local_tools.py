"""Temporary tool layer for the ReAct loop (S3.4).

Stand-in for Malak's S3.3 build_tools(). Same four tool NAMES so her version
can be dropped in later without touching the loop:
    searchKB, addworknote, suggestAnswer, requestHR

Write-back is NOT wired here: terminal tools only record the outcome in the
RunContext. Nothing can resolve, close or reassign an incident.
"""

from typing import Any, Callable

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.agent.run_context import RunContext

MAX_CHUNK_CHARS = 800  # keep observations small for the LLM
ALLOWED_TOOL_NAMES = {"searchKB", "addworknote", "suggestAnswer", "requestHR"}
TERMINAL_TOOLS = {"suggestAnswer", "requestHR"}


class SearchKBArgs(BaseModel):
    query: str = Field(description="Short search query describing the technical symptom.")


class AddWorkNoteArgs(BaseModel):
    note: str = Field(description="Internal work note text.")


class SuggestAnswerArgs(BaseModel):
    procedure: str = Field(
        description="Numbered procedure, one step per line, each step ending with "
                    "its source like [Article: KB0010001]."
    )
    sources: list[str] = Field(description="Article IDs the procedure is based on.")


class RequestHRArgs(BaseModel):
    reason: str = Field(description="Why a human must handle this incident.")


def build_local_tools(ctx: RunContext, retriever: Any) -> list[StructuredTool]:
    """retriever must expose .retrieve(query) -> dict (agent.agent.KnowledgeRetriever)."""

    def search_kb(query: str) -> dict:
        if ctx.finished:
            return {"error": "run already finished"}
        result = retriever.retrieve(query)
        if result.get("error"):
            return {"error": result["error"], "relevant": False}
        chunks = result.get("chunks") or []
        ctx.record_search(query, chunks, result.get("best_score"))
        return {
            "relevant": bool(chunks),
            "max_score": result.get("best_score"),
            "threshold": result.get("threshold"),
            "results": [
                {
                    "article_id": c["article_id"],
                    "title": c["title"],
                    "score": c["score"],
                    "text": (c.get("content") or "")[:MAX_CHUNK_CHARS],
                }
                for c in chunks
            ],
        }

    def add_work_note(note: str) -> dict:
        if ctx.finished:
            return {"error": "run already finished"}
        if not note or not note.strip():
            return {"error": "note must not be empty"}
        ctx.work_notes.append(note.strip())
        return {"ok": True}

    def suggest_answer(procedure: str, sources: list[str]) -> dict:
        if ctx.finished:
            return {"error": "run already finished"}
        ctx.finished = True
        ctx.outcome = "suggested"
        ctx.final_payload = {"procedure": procedure, "sources": sources}
        return {"ok": True, "status": "suggested"}

    def request_hr(reason: str) -> dict:
        if ctx.finished:
            return {"error": "run already finished"}
        if not reason or not reason.strip():
            return {"error": "reason must not be empty"}
        ctx.finished = True
        ctx.outcome = "escalated"
        ctx.final_payload = {"reason": reason.strip()}
        return {"ok": True, "status": "escalated"}

    def make(fn: Callable, name: str, schema: type[BaseModel], desc: str) -> StructuredTool:
        return StructuredTool.from_function(func=fn, name=name, args_schema=schema, description=desc)

    return [
        make(search_kb, "searchKB", SearchKBArgs,
             "Search published knowledge base articles. Returns relevant=true only if a chunk passed the score threshold."),
        make(add_work_note, "addworknote", AddWorkNoteArgs,
             "Add an internal work note to the incident. Not terminal."),
        make(suggest_answer, "suggestAnswer", SuggestAnswerArgs,
             "TERMINAL. Submit a grounded, numbered fix for human approval. Only after searchKB returned relevant=true."),
        make(request_hr, "requestHR", RequestHRArgs,
             "TERMINAL. Hand the incident to a human when the knowledge base has no reliable answer."),
    ]
