"""Incident pipeline: sanitized context -> ReAct agent -> grounded answer or escalation.

Called by the webhook background task (process_incident), or locally:
    python run_pipeline.py "wifi keeps disconnecting on my laptop"

S3.4: the one-shot LLM call was replaced by the ReAct agent loop
(src/agent/react_agent.py). Output shape (trace, result payload, outputs/ files)
is unchanged, so the webhook needs no change.

WHO WRITES TO SERVICENOW: the agent's own tools (suggestAnswer / requestHR /
addworknote) do the write-back through the write-back port (src/agent/factory.py).
process_incident() itself sends nothing to ServiceNow; it only returns and logs
the result.
"""

import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.agent.factory import build_agent_tools, new_run_context
from src.agent.react_agent import AgentFailure, AgentResult, run_agent
from App.resolved_incident_cache import ResolvedIncidentCache
from Schemas.Incident_context import IncidentContext
from Services.exporters import to_html, to_json, to_markdown
from Services.query_normalizer import normalize_incident
from Services.incident_preparer import IncidentContextPreparer
from Services.response_formatter import (
    FormattedResponse,
    build_escalation,
    format_response,
    to_writeback_payload,
)
from utils.console_tracer import print_execution_trace

load_dotenv()
logger = logging.getLogger(__name__)
from langfuse import observe, propagate_attributes, get_client

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


@observe()
def process_incident(ctx: IncidentContext) -> dict:
    """One incident, one run. Returns the result payload (human review always set).

    The ServiceNow write-back has already been done by the agent tools by the time
    this returns; nothing is sent to ServiceNow from this function.
    """
    number = ctx.original_number
    
    with propagate_attributes(session_id=number, tags=["worker"]):
        result: AgentResult | None = None
        chunks: list[dict] = []

        if not ctx.is_safe:
            # Guardrail from Sprint 2: never let a flagged payload reach the agent
            response = build_escalation("The incident text was flagged as unsafe.", number)
        else:
            # --- Exact-Match Redis Cache Lookup ---
            short_desc = getattr(ctx, "short_description", "")
            desc = getattr(ctx, "description", "")
            if not short_desc and ctx.sanitized_query:
                parts = ctx.sanitized_query.split("\n", 1)
                short_desc = parts[0]
                desc = parts[1] if len(parts) > 1 else ctx.truncated_description

            cached_data = ResolvedIncidentCache.get_cached_resolution(short_desc, desc)
            if cached_data:
                logger.info(
                    "[CACHE HIT] Exact-match verified resolution found in Redis for incident %s (sys_id: %s).",
                    number,
                    ctx.sys_id,
                )
                logger.info(
                    "[CACHE HIT] Returning verified solution from previously resolved ServiceNow incident %s.",
                    cached_data.get("number"),
                )
                try:
                    from utils.console_tracer import print_cache_hit_trace
                    print_cache_hit_trace(ctx, cached_data)
                except Exception as t_exc:
                    logger.debug("Console trace print warning: %s", t_exc)

                resolution_text = cached_data.get("close_notes", "")
                confidence = float(cached_data.get("ai_confidence") or 1.0)

                # --- Write back cached resolution to ServiceNow ---
                try:
                    from src.agent.factory import get_write_back_port
                    wb = get_write_back_port()
                    wb_res = wb.suggest(
                        sys_id=ctx.sys_id,
                        number=number,
                        payload={
                            "ai_suggested_response": resolution_text,
                            "ai_confidence": confidence,
                        },
                    )
                    logger.info(
                        "ServiceNow write-back for cached incident %s: %s",
                        number,
                        wb_res,
                    )
                    cached_num = cached_data.get("number")
                    note = (
                        f"[AI CACHE HIT] Verified solution populated from previously "
                        f"resolved incident {cached_num or 'historical database'}."
                    )
                    wb.add_work_note(sys_id=ctx.sys_id, number=number, note=note)
                except Exception as wb_exc:
                    logger.warning(
                        "ServiceNow write-back for cached incident %s failed: %s",
                        number,
                        wb_exc,
                    )

                payload = {
                    "source": "previously_resolved_incident",
                    "verified": True,
                    "resolution": resolution_text,
                    "ai_suggested_response": resolution_text,
                    "ai_confidence": confidence,
                    "human_review_required": True,
                    "escalated": False,
                    "citations": [],
                    "cached": True,
                    "cached_incident_number": cached_data.get("number"),
                    "cached_sys_id": cached_data.get("sys_id"),
                }
                out = Path("outputs")
                out.mkdir(exist_ok=True)
                (out / f"{number}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
                return payload

            # --- CACHE MISS: continue existing AI pipeline unchanged ---
            logger.info(
                "[CACHE MISS] Exact-match Redis lookup miss for incident %s. Proceeding with AI pipeline.",
                number,
            )
            raw_text = ctx.sanitized_query or ctx.truncated_description
            normalized = normalize_incident(raw_text)
            
            run_ctx = new_run_context(ctx.sys_id, number)
            # Store clean search query in run context so tools have accesss
            run_ctx.initial_search_query = normalized.optimized_search_query
            tools = build_agent_tools(run_ctx)  # S3.3 tools: searchKB, addworknote, suggestAnswer, requestHR
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
        # Log only. The agent tools already wrote to ServiceNow; this payload is NOT sent anywhere.
        logger.info(
            "Pipeline result for %s (log only, not sent to ServiceNow): %s",
            number,
            json.dumps(payload),
        )

    out = Path("outputs")
    out.mkdir(exist_ok=True)
    (out / f"{number}.md").write_text(to_markdown(response), encoding="utf-8")
    (out / f"{number}.html").write_text(to_html(response), encoding="utf-8")
    (out / f"{number}.json").write_text(to_json(response, confidence), encoding="utf-8")
    try:
        get_client().flush()
    except Exception as exc:
        logger.warning("Langfuse flush warning: %s", exc)
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