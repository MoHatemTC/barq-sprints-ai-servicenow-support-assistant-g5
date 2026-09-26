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
    
    # Retrieval and Observation State
    retrieved_chunks: List[Dict[str, Any]] = Field(default_factory=list, description="All chunks retrieved during run")
    retrieval_history: List[Dict[str, Any]] = Field(default_factory=list, description="Audit log of searchKB queries")
    best_score: float = Field(default=0.0, description="Highest retrieval score across all searches in this run")
    
    # Audit Trail
    work_notes: List[str] = Field(default_factory=list, description="Work notes submitted during this run")
    terminal_tool: Optional[str] = Field(default=None, description="Name of terminal tool invoked")
    terminal_payload: Optional[Dict[str, Any]] = Field(default=None, description="Payload submitted by terminal tool")

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

    def mark_finished(self, tool_name: str, payload: Dict[str, Any]) -> None:
        """Lock the run context when a terminal tool succeeds."""
        self.is_finished = True
        self.terminal_tool = tool_name
        self.terminal_payload = payload

    def get_known_article_ids(self) -> Set[str]:
        """Return the set of article numbers retrieved in this run."""
        return {
            str(c.get("article_id"))
            for c in self.retrieved_chunks
            if c.get("article_id")
        }

    def check_finished(self) -> Optional[Dict[str, Any]]:
        """Return a structured error observation if the run is already finished."""
        if self.is_finished:
            return {
                "status": "error",
                "code": "RUN_ALREADY_FINISHED",
                "error": f"Incident run {self.number} is already finished. No further tool executions are permitted.",
            }
        return None
