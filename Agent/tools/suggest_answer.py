"""suggestAnswer tool implementation for Sprint 3.3.

Terminal tool validating that the procedure is a numbered list and sources are cited,
verifying cited sources against retrieved articles in RunContext, formatting the response,
calculating ai_confidence from retrieval scores, and calling suggest via WriteBackPort.

State & Terminal Semantics:
- On success: marks RunContext.is_finished = True, blocking further tool execution.
- On write-back failure: keeps run open for retry, returning a structured error observation.
"""

import logging
from typing import Any, Dict, List, Optional

from agent.formatting import (
    calculate_ai_confidence,
    format_suggested_resolution,
    validate_numbered_procedure,
    validate_step_citations,
)
from agent.ports import WriteBackPort
from agent.run_context import RunContext

logger = logging.getLogger("agent.tools.suggest_answer")


class SuggestAnswerTool:
    """Terminal tool submitting an AI-drafted procedural resolution."""

    def __init__(self, run_context: RunContext, write_back_port: WriteBackPort):
        self.run_context = run_context
        self.write_back_port = write_back_port

    def __call__(self, procedure: str, sources: Optional[List[str]] = None) -> Dict[str, Any]:
        return self.run(procedure=procedure, sources=sources)

    def run(self, procedure: str, sources: Optional[List[str]] = None) -> Dict[str, Any]:
        """Execute suggestAnswer."""
        # 1. State check: Enforce terminal semantics
        finish_check = self.run_context.check_finished()
        if finish_check:
            return finish_check

        # 2. Validation: Procedure must be a numbered list
        valid_proc, steps, proc_err = validate_numbered_procedure(procedure)
        if not valid_proc:
            return {
                "status": "error",
                "error": f"Validation failed: {proc_err}",
                "incident_number": self.run_context.number,
            }

        # 3. Validation: Citations must be inline and match retrieved articles in RunContext
        known_articles = self.run_context.get_known_article_ids()
        valid_citations, cited_sources, rejected, cite_err = validate_step_citations(
            steps=steps, known_article_ids=known_articles
        )
        if not valid_citations:
            return {
                "status": "error",
                "error": f"Grounding validation failed: {cite_err}",
                "rejected_steps": rejected,
                "incident_number": self.run_context.number,
            }

        # Combine explicitly supplied sources and cited sources
        final_sources = list(dict.fromkeys((sources or []) + cited_sources))

        # 4. Calculate AI Confidence (0.0 to 1.0) strictly from retrieval scores
        retrieval_scores = [
            float(c.get("score", 0.0))
            for c in self.run_context.retrieved_chunks
        ]
        # Include best_score in case chunks array was cleared
        if self.run_context.best_score > 0.0:
            retrieval_scores.append(self.run_context.best_score)

        ai_confidence = calculate_ai_confidence(retrieval_scores)

        # 5. Build standardized write-back payload
        formatted_resolution = format_suggested_resolution(steps, final_sources)
        writeback_payload = {
            "ai_suggested_response": formatted_resolution,
            "ai_confidence": ai_confidence,
            "human_review_required": True,  # Mandatory HITL governance
            "escalated": False,
            "citations": final_sources,
            "steps_count": len(steps),
        }

        # 6. Execute Write-Back Call
        try:
            port_result = self.write_back_port.suggest(
                sys_id=self.run_context.sys_id,
                number=self.run_context.number,
                payload=writeback_payload,
            )

            # Success: Mark run finished and lock state
            self.run_context.mark_finished("suggestAnswer", writeback_payload)

            return {
                "status": "success",
                "message": f"Suggested resolution submitted for incident {self.run_context.number}.",
                "incident_number": self.run_context.number,
                "ai_confidence": ai_confidence,
                "citations": final_sources,
                "payload": writeback_payload,
                "port_result": port_result,
            }

        except Exception as exc:
            logger.exception("suggestAnswer write-back failed")
            # Failed write-back keeps the run OPEN for retry
            return {
                "status": "error",
                "error": f"Failed to submit suggested resolution via write-back port: {type(exc).__name__}: {str(exc)}",
                "incident_number": self.run_context.number,
                "ai_confidence": ai_confidence,
            }
