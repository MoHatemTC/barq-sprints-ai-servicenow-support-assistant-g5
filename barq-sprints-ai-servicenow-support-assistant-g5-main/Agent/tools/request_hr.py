"""requestHR tool implementation for Sprint 3.3.

Terminal tool validating escalation reason and calling escalate via WriteBackPort.

State & Terminal Semantics:
- On success: marks RunContext.is_finished = True, blocking further tool execution.
- On write-back failure: returns an error observation with code WRITEBACK_FAILED. The
  ReAct loop stops on the first one (no retries against a failing ServiceNow).
"""

import logging
from typing import Any, Dict
from ..config import MIN_REASON_LENGTH, WRITEBACK_FAILED_CODE
from ..formatting import calculate_ai_confidence, format_escalation_message
from ..ports import WriteBackPort
from ..run_context import RunContext

logger = logging.getLogger("agent.tools.request_hr")


class RequestHRTool:
    """Terminal tool requesting Human Review / Escalation."""

    def __init__(
        self,
        run_context: RunContext,
        write_back_port: WriteBackPort,
        min_reason_length: int = MIN_REASON_LENGTH,
    ):
        self.run_context = run_context
        self.write_back_port = write_back_port
        self.min_reason_length = min_reason_length

    def __call__(self, reason: str) -> Dict[str, Any]:
        return self.run(reason)

    def run(self, reason: str) -> Dict[str, Any]:
        """Execute requestHR."""
        # 1. State check: Enforce terminal semantics
        finish_check = self.run_context.check_finished()
        if finish_check:
            return finish_check

        # 2. Input validation
        if not reason or not reason.strip():
            return {
                "status": "error",
                "error": "Validation failed: Escalation reason cannot be empty.",
                "incident_number": self.run_context.number,
            }

        cleaned_reason = reason.strip()
        if len(cleaned_reason) < self.min_reason_length:
            return {
                "status": "error",
                "error": (
                    f"Validation failed: Escalation reason is too short "
                    f"(minimum {self.min_reason_length} characters required)."
                ),
                "incident_number": self.run_context.number,
            }

        # 3. Dynamically calculate AI Confidence from retrieval scores
        retrieval_scores = [
            float(c.get("score", 0.0))
            for c in self.run_context.retrieved_chunks
        ]
        if self.run_context.best_score > 0.0:
            retrieval_scores.append(self.run_context.best_score)

        ai_confidence = calculate_ai_confidence(retrieval_scores)

        # 4. Build escalation payload
        escalation_text = format_escalation_message(
            incident_number=self.run_context.number, reason=cleaned_reason
        )

        writeback_payload = {
            "ai_suggested_response": escalation_text,
            "ai_confidence": ai_confidence,
            "human_review_required": True,
            "escalated": True,
            "reason": cleaned_reason,
            "citations": [],
        }

        # 5. Execute Write-Back Call
        try:
            port_result = self.write_back_port.escalate(
                sys_id=self.run_context.sys_id,
                number=self.run_context.number,
                reason=cleaned_reason,
                payload=writeback_payload,
            )

            # Check if write-back port returned an explicit error/failure payload
            if isinstance(port_result, dict) and (
                port_result.get("status") in ("error", "failed")
                or port_result.get("success") is False
            ):
                # Write-back failed: report it with a code; the loop stops here.
                return {
                    "status": "error",
                    "code": WRITEBACK_FAILED_CODE,
                    "error": f"Write-back port escalation failed: {port_result.get('error', 'Operation unconfirmed')}",
                    "incident_number": self.run_context.number,
                    "port_result": port_result,
                }

            # Success: Explicitly update active run context to finished to block subsequent tool calls
            self.run_context.mark_finished("requestHR", writeback_payload)

            return {
                "status": "success",
                "message": f"Escalation to human review submitted for incident {self.run_context.number}.",
                "incident_number": self.run_context.number,
                "reason": cleaned_reason,
                "ai_confidence": ai_confidence,
                "payload": writeback_payload,
                "port_result": port_result,
            }

        except Exception as exc:
            logger.exception("requestHR write-back failed")
            # Write-back raised: same code, the loop stops here.
            return {
                "status": "error",
                "code": WRITEBACK_FAILED_CODE,
                "error": f"Failed to escalate incident via write-back port: {type(exc).__name__}: {str(exc)}",
                "incident_number": self.run_context.number,
            }
