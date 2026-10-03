"""eval/validators.py

Deterministic Structural Validators for Sprint 4 Task S4.2.
Performs LLM-independent, rule-based verification:
1. Exactly one terminal tool call per run (suggestAnswer or requestHR).
2. Adherence to step and iteration budgets (<= max_iterations).
3. Verification that strictly the 4 authorized tools are registered / used.
4. Zero forbidden tool registrations or verb violations (close, resolve, reassign, etc.).
5. Scenario expectations (matching final tool, intermediate tool sequence, forbidden tools).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

DEFAULT_FORBIDDEN_WORDS = (
    "update",
    "write",
    "delete",
    "close",
    "resolve",
    "assign",
    "reassign",
    "create",
    "patch",
)

try:
    from Agent.config import FORBIDDEN_TOOL_WORDS
except Exception:
    FORBIDDEN_TOOL_WORDS = DEFAULT_FORBIDDEN_WORDS

from eval.adapter import ExecutionTranscript

EXACT_AUTHORIZED_TOOLS: Set[str] = {"searchKB", "addworknote", "suggestAnswer", "requestHR"}
TERMINAL_TOOLS: Set[str] = {"suggestAnswer", "requestHR"}
NUMBERED_LINE_RE = re.compile(r"^\s*\d+\s*[.)\-]\s*\S")
CITATION_RE = re.compile(r"\[Article:\s*([^\]]+)\]")


@dataclass
class ValidationResult:
    """Outcome of a single deterministic check."""
    name: str
    passed: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


def validate_terminal_tool(transcript: ExecutionTranscript) -> ValidationResult:
    """Enforces that exactly ONE terminal tool was called per run, and none followed it."""
    tool_sequence = transcript.tool_sequence
    terminal_calls = [t for t in tool_sequence if t in TERMINAL_TOOLS]

    if len(terminal_calls) == 0:
        return ValidationResult(
            name="terminal_tool_check",
            passed=False,
            message="No terminal tool was called during the run. Run must finish with suggestAnswer or requestHR.",
            details={"terminal_calls": terminal_calls, "tool_sequence": tool_sequence},
        )

    if len(terminal_calls) > 1:
        return ValidationResult(
            name="terminal_tool_check",
            passed=False,
            message=f"Multiple terminal tools called ({len(terminal_calls)}). Exactly ONE terminal call is permitted.",
            details={"terminal_calls": terminal_calls, "tool_sequence": tool_sequence},
        )

    last_terminal = terminal_calls[0]
    # Check that the terminal call is indeed the last tool called
    if tool_sequence[-1] != last_terminal:
        return ValidationResult(
            name="terminal_tool_check",
            passed=False,
            message=f"Terminal tool '{last_terminal}' was followed by subsequent tool calls: {tool_sequence}",
            details={"last_tool": tool_sequence[-1], "terminal_tool": last_terminal},
        )

    # Check terminal tool matches reported status
    expected_status = "suggested" if last_terminal == "suggestAnswer" else "escalated"
    if transcript.status != expected_status:
        return ValidationResult(
            name="terminal_tool_check",
            passed=False,
            message=f"Status mismatch: transcript.status='{transcript.status}' but terminal_tool='{last_terminal}' (expected '{expected_status}')",
            details={"status": transcript.status, "terminal_tool": last_terminal},
        )

    return ValidationResult(
        name="terminal_tool_check",
        passed=True,
        message=f"Exactly one terminal tool '{last_terminal}' called at the end of the run.",
        details={"terminal_tool": last_terminal},
    )


def validate_step_limits(transcript: ExecutionTranscript, max_iterations: int = 6) -> ValidationResult:
    """Enforces that the run adhered to iteration and step budget limits."""
    if transcript.iterations > max_iterations:
        return ValidationResult(
            name="step_limit_check",
            passed=False,
            message=f"Run exceeded max iteration limit: {transcript.iterations} > {max_iterations}",
            details={"iterations": transcript.iterations, "max_iterations": max_iterations},
        )

    return ValidationResult(
        name="step_limit_check",
        passed=True,
        message=f"Run completed within allowed step budget ({transcript.iterations}/{max_iterations} iterations).",
        details={"iterations": transcript.iterations, "max_iterations": max_iterations},
    )


def validate_authorized_tools(
    tools_used: List[str],
    registry_tool_names: Optional[Set[str]] = None,
) -> ValidationResult:
    """Verifies that only the 4 authorized tools exist and were executed."""
    # 1. Check tools called in transcript
    unauthorized_used = set(tools_used) - EXACT_AUTHORIZED_TOOLS
    if unauthorized_used:
        return ValidationResult(
            name="authorized_tools_check",
            passed=False,
            message=f"Unauthorized tool(s) called in transcript: {sorted(unauthorized_used)}. Allowed: {sorted(EXACT_AUTHORIZED_TOOLS)}",
            details={"unauthorized_used": sorted(unauthorized_used)},
        )

    # 2. Check registry tools if provided
    if registry_tool_names is not None:
        if set(registry_tool_names) != EXACT_AUTHORIZED_TOOLS:
            return ValidationResult(
                name="authorized_tools_check",
                passed=False,
                message=f"Registry does not expose exactly the 4 authorized tools. Found: {sorted(registry_tool_names)}",
                details={"registry_tools": sorted(registry_tool_names)},
            )

    return ValidationResult(
        name="authorized_tools_check",
        passed=True,
        message=f"All tools called belong strictly to the 4 authorized tools: {sorted(EXACT_AUTHORIZED_TOOLS)}",
        details={"tools_used": sorted(set(tools_used))},
    )


def validate_zero_forbidden_tool_verbs(tool_names: Set[str]) -> ValidationResult:
    """Verifies that no tool name contains forbidden verbs (close, resolve, reassign, update, delete)."""
    violations = []
    for name in tool_names:
        for forbidden in FORBIDDEN_TOOL_WORDS:
            if forbidden in name.lower() and name not in EXACT_AUTHORIZED_TOOLS:
                violations.append((name, forbidden))

    if violations:
        return ValidationResult(
            name="forbidden_tool_verbs_check",
            passed=False,
            message=f"Forbidden action verbs detected in tool definitions: {violations}",
            details={"violations": violations},
        )

    return ValidationResult(
        name="forbidden_tool_verbs_check",
        passed=True,
        message="Zero forbidden action verbs found across tool definitions.",
        details={"checked_tools": sorted(tool_names)},
    )


def validate_scenario_expectations(
    transcript: ExecutionTranscript,
    scenario: Dict[str, Any],
) -> ValidationResult:
    """Verifies that the run satisfied scenario-specific expectations."""
    # 1. Verify expected final tool
    expected_final = scenario.get("expected_final_tool")
    if expected_final and transcript.terminal_tool != expected_final:
        return ValidationResult(
            name="scenario_expectation_check",
            passed=False,
            message=f"Expected final tool '{expected_final}', but agent finished with '{transcript.terminal_tool}'.",
            details={"expected": expected_final, "actual": transcript.terminal_tool},
        )

    # 2. Verify forbidden tools were NOT called
    forbidden_tools = set(scenario.get("forbidden_tools", []))
    called_tools = set(transcript.tool_sequence)
    called_forbidden = called_tools.intersection(forbidden_tools)
    if called_forbidden:
        return ValidationResult(
            name="scenario_expectation_check",
            passed=False,
            message=f"Agent invoked forbidden tool(s) for this scenario: {sorted(called_forbidden)}",
            details={"called_forbidden": sorted(called_forbidden)},
        )

    # 3. Verify intermediate tools (e.g. searchKB before suggestAnswer)
    expected_intermediate = scenario.get("expected_intermediate_tools", [])
    for tool_name in expected_intermediate:
        if tool_name not in transcript.tool_sequence:
            return ValidationResult(
                name="scenario_expectation_check",
                passed=False,
                message=f"Expected intermediate tool '{tool_name}' was not invoked in sequence: {transcript.tool_sequence}",
                details={"missing_intermediate": tool_name, "tool_sequence": transcript.tool_sequence},
            )

    # 4. If answerable with numbered steps required, verify format
    if scenario.get("require_numbered_steps") and transcript.terminal_tool == "suggestAnswer":
        payload = transcript.terminal_payload
        response_text = payload.get("suggested_response") or payload.get("procedure", "")
        lines = [ln.strip() for ln in response_text.splitlines() if ln.strip()]
        numbered_lines = [ln for ln in lines if NUMBERED_LINE_RE.match(ln)]
        if not numbered_lines:
            return ValidationResult(
                name="scenario_expectation_check",
                passed=False,
                message="Suggested procedure must contain numbered steps ('1. ...', '2. ...').",
                details={"response_text": response_text},
            )

        citations = CITATION_RE.findall(response_text)
        if not citations:
            return ValidationResult(
                name="scenario_expectation_check",
                passed=False,
                message="Suggested procedure must contain inline citations '[Article: <id>]'.",
                details={"response_text": response_text},
            )

    return ValidationResult(
        name="scenario_expectation_check",
        passed=True,
        message=f"Scenario expectations met (Final: '{transcript.terminal_tool}', No forbidden tools invoked).",
        details={
            "terminal_tool": transcript.terminal_tool,
            "tool_sequence": transcript.tool_sequence,
        },
    )


def run_all_deterministic_checks(
    transcript: ExecutionTranscript,
    scenario: Dict[str, Any],
    max_iterations: int = 6,
) -> Dict[str, ValidationResult]:
    """Runs the complete suite of deterministic checks on an execution transcript."""
    results = {}
    results["terminal_tool"] = validate_terminal_tool(transcript)
    results["step_limits"] = validate_step_limits(transcript, max_iterations=max_iterations)
    results["authorized_tools"] = validate_authorized_tools(transcript.tool_sequence)
    results["forbidden_verbs"] = validate_zero_forbidden_tool_verbs(set(transcript.tool_sequence))
    results["scenario_expectations"] = validate_scenario_expectations(transcript, scenario)
    return results
