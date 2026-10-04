"""Incident Run Context for Sprint 3.3 Agent Tool Layer.

Defines the RunContext Pydantic class that locks in sys_id, number,
tracks retrieval ledger, work notes, and manages the is_finished state flag.
"""

from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field


class RunContext(BaseModel):
    """Execution context bound to a single incident run.
    
    Locks in the incident sys_id and number, records retrieval states and work notes,
    and enforces terminal state semantics via `is_finished`.
    """
    sys_id: str = Field(..., description="ServiceNow 32-character Sys ID")
    number: str = Field(..., description="Incident identifier, e.g., INC0010001")
    is_finished: bool = Field(default=False, description="Flag indicating if a terminal tool has completed")
    is_completed: bool = Field(default=False, description="Explicit flag indicating if incident run is completed")
    status: str = Field(default="in_progress", description="Run lifecycle state ('in_progress' or 'completed')")
    
    # Retrieval and Observation State
    retrieved_chunks: List[Dict[str, Any]] = Field(default_factory=list, description="All chunks retrieved during run")
    retrieval_history: List[Dict[str, Any]] = Field(default_factory=list, description="Audit log of searchKB queries")
    best_score: float = Field(default=0.0, description="Highest retrieval score across all searches in this run")
    
    # Audit Trail
    work_notes: List[str] = Field(default_factory=list, description="Work notes submitted during this run")
    terminal_tool: Optional[str] = Field(default=None, description="Name of terminal tool invoked")
    terminal_payload: Optional[Dict[str, Any]] = Field(default=None, description="Payload submitted by terminal tool")

    # ReAct loop execution log (S3.4): llm / tool / guardrail / fallback events
    events: List[Dict[str, Any]] = Field(default_factory=list, description="Ordered execution steps of the agent loop")

    # Pre-normalized query set by run_pipeline before the agent starts
    initial_search_query: Optional[str] = Field(default=None, description="Normalized/optimized search query derived from the incident text")

    def record_retrieval(self, query: str, chunks: List[Dict[str, Any]], best_score: float) -> None:
        """Record the results of a searchKB query."""
        self.retrieval_history.append({
            "query": query,
            "chunks_count": len(chunks),
            "best_score": best_score,
        })
        for chunk in chunks:
            # Deduplicate by article_id and chunk_index if present
            chunk_id = (chunk.get("article_id"), chunk.get("chunk_index"))
            existing_ids = {
                (c.get("article_id"), c.get("chunk_index"))
                for c in self.retrieved_chunks
            }
            if chunk_id not in existing_ids:
                self.retrieved_chunks.append(chunk)

        if best_score > self.best_score:
            self.best_score = round(float(best_score), 4)

    def record_work_note(self, note: str) -> None:
        """Record an added work note to audit history."""
        self.work_notes.append(note)

    def mark_completed(self, tool_name: str, payload: Dict[str, Any]) -> None:
        """Explicitly lock the run context as completed when a terminal tool succeeds."""
        self.is_finished = True
        self.is_completed = True
        self.status = "completed"
        self.terminal_tool = tool_name
        self.terminal_payload = payload

    def mark_finished(self, tool_name: str, payload: Dict[str, Any]) -> None:
        """Alias for mark_completed to maintain backward compatibility."""
        self.mark_completed(tool_name, payload)

    def get_known_article_ids(self) -> Set[str]:
        """Return the set of article numbers retrieved in this run."""
        return {
            str(c.get("article_id"))
            for c in self.retrieved_chunks
            if c.get("article_id")
        }

    def check_finished(self) -> Optional[Dict[str, Any]]:
        """Return a structured error observation if the run is already completed/finished."""
        if self.is_finished or self.is_completed or self.status == "completed":
            return {
                "status": "error",
                "code": "RUN_ALREADY_FINISHED",
                "error": f"Incident run {self.number} is already completed/finished. No further tool executions are permitted.",
            }
        return None

    def check_completed(self) -> Optional[Dict[str, Any]]:
        """Alias for check_finished."""
        return self.check_finished()

    # ------------------------------------------------------------------ #
    # S3.4 ReAct loop view (read-only helpers; the tools above are unchanged)
    # ------------------------------------------------------------------ #
    def log(self, kind: str, **data: Any) -> None:
        """Append one step to the execution log."""
        self.events.append({"step": len(self.events) + 1, "kind": kind, **data})

    @property
    def incident_number(self) -> str:
        return self.number

    @property
    def finished(self) -> bool:
        return self.is_finished or self.is_completed or self.status == "completed"

    @property
    def outcome(self) -> Optional[str]:
        """'suggested' | 'escalated' | None, derived from the terminal tool."""
        return {"suggestAnswer": "suggested", "requestHR": "escalated"}.get(self.terminal_tool or "")

    @property
    def final_payload(self) -> Dict[str, Any]:
        return self.terminal_payload or {}

    @property
    def max_score(self) -> float:
        return self.best_score

    @property
    def any_relevant(self) -> bool:
        """True once any searchKB call returned a chunk above the threshold."""
        return bool(self.retrieved_chunks)

    @property
    def retrieved(self) -> Dict[str, List[Dict[str, Any]]]:
        """Relevant chunks grouped by article id (used by the grounding gate)."""
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for chunk in self.retrieved_chunks:
            if chunk.get("article_id"):
                grouped.setdefault(str(chunk["article_id"]), []).append(chunk)
        return grouped

    def all_chunks(self) -> List[Dict[str, Any]]:
        """Relevant chunks, best score first."""
        return sorted(self.retrieved_chunks, key=lambda c: float(c.get("score", 0.0)), reverse=True)