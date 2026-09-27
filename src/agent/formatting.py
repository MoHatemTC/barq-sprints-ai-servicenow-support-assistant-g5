"""src.agent.formatting re-exporting agent.formatting."""

from agent.formatting import (
    CITATION_RE,
    STEP_NUMBER_PREFIX_RE,
    calculate_ai_confidence,
    format_escalation_message,
    format_suggested_resolution,
    validate_numbered_procedure,
    validate_step_citations,
)

__all__ = [
    "CITATION_RE",
    "STEP_NUMBER_PREFIX_RE",
    "validate_numbered_procedure",
    "validate_step_citations",
    "calculate_ai_confidence",
    "format_suggested_resolution",
    "format_escalation_message",
]
