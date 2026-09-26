"""addworknote tool implementation for Sprint 3.3.

Non-terminal tool validating note length and calling add_work_note via the write-back port.
On success, records the note in RunContext. On failure, handles errors cleanly as
structured observations and leaves the run open for retry.
"""

import logging
from typing import Any, Dict
from agent.config import MAX_NOTE_LENGTH
from agent.ports import WriteBackPort
from agent.run_context import RunContext

logger = logging.getLogger("agent.tools.add_worknote")


class AddWorkNoteTool:
    """Tool class implementing addworknote bound to RunContext and WriteBackPort."""

    def __init__(
        self,
        run_context: RunContext,
        write_back_port: WriteBackPort,
        max_note_length: int = MAX_NOTE_LENGTH,
    ):
        self.run_context = run_context
        self.write_back_port = write_back_port
        self.max_note_length = max_note_length

    def __call__(self, note: str) -> Dict[str, Any]:
        return self.run(note)

    def run(self, note: str) -> Dict[str, Any]:
        """Execute addworknote."""
        # 1. State check: Enforce terminal semantics
        finish_check = self.run_context.check_finished()
        if finish_check:
            return finish_check

        # 2. Input validation
        if not note or not note.strip():
            return {
                "status": "error",
                "error": "Validation failed: Work note cannot be empty.",
                "incident_number": self.run_context.number,
            }

        cleaned_note = note.strip()
        if len(cleaned_note) > self.max_note_length:
            return {
                "status": "error",
                "error": (
                    f"Validation failed: Note length ({len(cleaned_note)}) exceeds "
                    f"maximum allowed limit of {self.max_note_length} characters."
                ),
                "incident_number": self.run_context.number,
            }

        # 3. Call Write-Back Port with exception safety
        try:
            port_result = self.write_back_port.add_work_note(
                sys_id=self.run_context.sys_id,
                number=self.run_context.number,
                note=cleaned_note,
            )

            # Record in RunContext
            self.run_context.record_work_note(cleaned_note)

            return {
                "status": "success",
                "message": f"Work note added to incident {self.run_context.number}.",
                "incident_number": self.run_context.number,
                "note_length": len(cleaned_note),
                "port_result": port_result,
            }

        except Exception as exc:
            logger.exception("addworknote write-back failed")
            return {
                "status": "error",
                "error": f"Failed to post work note via write-back port: {type(exc).__name__}: {str(exc)}",
                "incident_number": self.run_context.number,
            }
