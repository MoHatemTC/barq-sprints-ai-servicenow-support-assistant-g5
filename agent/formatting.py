"""Formatting and validation utilities for Agent Tool Layer (Sprint 3.3).

Contains logic to:
1. Validate numbered procedures.
2. Validate and enforce citations against known retrieved articles.
3. Calculate AI confidence (0.0 to 1.0) strictly from retrieval similarity scores.
4. Render standardized resolutions and escalations.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

# Matches [Article: KB0010001] or [KB0010001]
CITATION_RE = re.compile(r"\[(?:Article:\s*)?([A-Za-z]{2,}\d+)\]")

# Matches lines starting with numbers like "1.", "1)", "1 - "
STEP_NUMBER_PREFIX_RE = re.compile(r"^\s*(\d+)[\.\)\-]\s*(.*)$")


def validate_numbered_procedure(procedure: str) -> Tuple[bool, List[str], Optional[str]]:
    """Validate that the procedure text is a structured numbered list.
    
    Returns:
        (is_valid, parsed_steps, error_message)
    """
    if not procedure or not procedure.strip():
        return False, [], "Procedure cannot be empty. Must be a numbered list."

    lines = [ln.strip() for ln in procedure.strip().splitlines() if ln.strip()]
    if not lines:
        return False, [], "Procedure contains no valid lines."

    steps: List[str] = []
    expected_number = 1

    for line in lines:
        match = STEP_NUMBER_PREFIX_RE.match(line)
        if not match:
            # If a line doesn't start with a number, verify if it's an overall header or invalid
            return (
                False,
                [],
                f"Line '{line}' is not numbered. All procedure steps must start with a number (e.g., '1. ...').",
            )
        step_num = int(match.group(1))
        step_text = match.group(2).strip()

        if not step_text:
            return False, [], f"Step {step_num} is empty."

        steps.append(f"{step_num}. {step_text}")
        expected_number += 1

    if not steps:
        return False, [], "No numbered steps could be parsed from procedure."

    return True, steps, None


def validate_step_citations(
    steps: List[str], known_article_ids: Set[str]
) -> Tuple[bool, List[str], List[Dict[str, Any]], Optional[str]]:
    """Validate that every step has an inline citation and that all cited sources were retrieved.
    
    Returns:
        (is_valid, all_cited_sources, rejected_steps, error_message)
    """
    all_cited: List[str] = []
    rejected: List[Dict[str, Any]] = []

    for idx, step in enumerate(steps, start=1):
        citations = list(dict.fromkeys(CITATION_RE.findall(step)))
        if not citations:
            rejected.append({"step": step, "step_index": idx, "reason": "Missing inline citation"})
            continue

        unknown = [c for c in citations if c not in known_article_ids]
        if unknown:
            rejected.append({
                "step": step,
                "step_index": idx,
                "reason": f"Cited unknown/unretrieved source(s): {', '.join(unknown)}",
                "unknown_sources": unknown,
            })
            continue

        all_cited.extend(citations)

    # Deduplicate cited sources preserving order
    deduped_sources = list(dict.fromkeys(all_cited))

    if rejected:
        first_err = rejected[0]
        return False, deduped_sources, rejected, f"Step {first_err['step_index']} failed citation validation: {first_err['reason']}."

    return True, deduped_sources, [], None


def calculate_ai_confidence(scores: List[float]) -> float:
    """Calculate AI confidence strictly from retrieval similarity scores.
    
    Formula:
        ai_confidence = round(max(scores), 4) if scores else 0.0
    Clamped strictly between 0.0 and 1.0.
    """
    valid_scores = [
        float(s) for s in scores
        if isinstance(s, (int, float)) and not (isinstance(s, float) and s != s)  # exclude NaN
    ]
    if not valid_scores:
        return 0.0

    best = max(valid_scores)
    # Clamp between 0.0 and 1.0
    clamped = max(0.0, min(1.0, best))
    return round(clamped, 4)


def format_suggested_resolution(steps: List[str], sources: List[str]) -> str:
    """Format final suggested resolution text for human review."""
    lines = ["Suggested resolution (pending human approval):"]
    lines.extend(steps)
    if sources:
        lines.append("")
        lines.append("Sources:")
        for src in sources:
            lines.append(f"- {src}")
    return "\n".join(lines)


def format_escalation_message(incident_number: str, reason: str) -> str:
    """Format human review escalation message."""
    return (
        f"HUMAN REVIEW REQUIRED for incident {incident_number}: {reason} "
        "No resolution procedure was generated. "
        "Please escalate this incident to a service desk agent."
    )
