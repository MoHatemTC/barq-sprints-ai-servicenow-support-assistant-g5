"""Agent package exposing RunContext, tools, registry, and ports."""

from agent.config import (
    ALLOWED_WORKFLOW_STATES,
    MAX_NOTE_LENGTH,
    SCORE_THRESHOLD,
    TOP_K,
)
from agent.formatting import (
    calculate_ai_confidence,
    format_escalation_message,
    format_suggested_resolution,
    validate_numbered_procedure,
    validate_step_citations,
)
from agent.ports import FakeWriteBackPort, WriteBackPort
from agent.run_context import RunContext
from agent.tools import (
    AddWorkNoteTool,
    RequestHRTool,
    SearchKBTool,
    SuggestAnswerTool,
    ToolRegistry,
)

__all__ = [
    "RunContext",
    "ToolRegistry",
    "WriteBackPort",
    "FakeWriteBackPort",
    "SearchKBTool",
    "AddWorkNoteTool",
    "SuggestAnswerTool",
    "RequestHRTool",
    "validate_numbered_procedure",
    "validate_step_citations",
    "calculate_ai_confidence",
    "format_suggested_resolution",
    "format_escalation_message",
    "TOP_K",
    "SCORE_THRESHOLD",
    "MAX_NOTE_LENGTH",
    "ALLOWED_WORKFLOW_STATES",
]
