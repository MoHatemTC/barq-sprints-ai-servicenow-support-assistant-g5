"""Incident pipeline: sanitized context -> ReAct agent -> grounded answer or escalation.

Called by the webhook background task (process_incident), or locally:
    python run_pipeline.py "wifi keeps disconnecting on my laptop"

S3.4: the one-shot LLM call was replaced by the ReAct agent loop
(src/agent/react_agent.py). Output shape (trace, write-back payload, outputs/ files)
is unchanged, so the webhook needs no change.
"""

import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent.agent import get_knowledge_retriever
from src.agent.local_tools import build_local_tools
from src.agent.react_agent import AgentFailure, AgentResult, run_agent
from src.agent.run_context import RunContext
from Schemas.Incident_context import IncidentContext
from Services.exporters import to_html, to_json, to_markdown
from Services.incident_preparer import IncidentContextPreparer
from Services.response_formatter import (
    FormattedResponse,
    build_escalation,
    format_response,
    to_writeback_payload,
)
from utils.console_tracer import print_execution_trace

load_dotenv()
logger = logging.getLogger("servicenow_webhook.pipeline")


def agent_result_to_response(result: AgentResult, number: str) -> FormattedResponse:
    """Map the agent outcome onto the existing formatter (Sprint 2 Task 6)."""
    if result.outcome == "suggested" and result.procedure:
        # Second, independent citation check by the formatter (defence in depth)
        return format_response(
            result.procedure,
            result.retrieved_chunks,
            human_review_required=False,
            incident_number=number,
        )
    return build_escalation(result.reason or "The agent handed this incident to a human.", number)


def process_incident(ctx: IncidentContext) -> dict:
    """One incident, one run. Always returns a write-back payload with human review set."""
    number = ctx.original_number
    result: AgentResult | None = None
    chunks: list[dict] = []

    if not ctx.is_safe:
        # Guardrail from Sprint 2: never let a flagged payload reach the agent
        response = build_escalation("The incident text was flagged as unsafe.", number)
    else:
        run_ctx = RunContext(ctx.sys_id, number)
        tools = build_local_tools(run_ctx, get_knowledge_retriever())  # later: Malak's build_tools()
        try:
            result = run_agent(ctx.sys_id, ctx, tools, ctx=run_ctx)
            chunks = result.retrieved_chunks
            response = agent_result_to_response(result, number)
        except AgentFailure:
            logger.exception("Agent failed (LLM unavailable) for %s", number)
            response = build_escalation("The AI model is unavailable.", number)
        except Exception:
            # NFR-03: never crash the service; escalate and record
            logger.exception("Unexpected agent error for %s", number)
            response = build_escalation("An unexpected error occurred in the AI agent.", number)

    # FR-17: confidence = best retrieval score seen in the run (0.0 if none)
    confidence = round(result.max_score, 4) if result else 0.0

    print_execution_trace(ctx, chunks, response, confidence)
    payload = to_writeback_payload(response, confidence)
    payload["agent"] = {
        "prompt_version": result.prompt_version if result else None,
        "outcome": result.outcome if result else "escalated",
        "terminal_tool": result.terminal_tool if result else "requestHR",
        "iterations": result.iterations if result else 0,
        "searches": result.searches if result else 0,
        "grounding_rejections": result.grounding_rejections if result else 0,
        "fallback_reason": result.fallback_reason if result else None,
        "total_tokens": result.total_tokens if result else 0,
    }
    logger.info("Write-back payload for %s: %s", number, json.dumps(payload))

    # NEXT STEP: send `payload` to ServiceNow through the write-back client (S3.6).
    out = Path("outputs")
    out.mkdir(exist_ok=True)
    (out / f"{number}.md").write_text(to_markdown(response), encoding="utf-8")
    (out / f"{number}.html").write_text(to_html(response), encoding="utf-8")
    (out / f"{number}.json").write_text(to_json(response, confidence), encoding="utf-8")
    return payload


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    text = " ".join(sys.argv[1:]) or "wifi keeps disconnecting on my laptop"

    # Run the real guardrails, same as the webhook does
    ctx = IncidentContextPreparer().process_payload(
        sys_id="0" * 32,
        number="INC0000000",
        short_desc=text,
        desc="",
    )
    print(json.dumps(process_incident(ctx), indent=2))


if __name__ == "__main__":
    main()
