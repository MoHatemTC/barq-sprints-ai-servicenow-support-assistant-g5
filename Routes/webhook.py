import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from schemas.webhook_schema import IncidentPayload
from App.auth import verify_webhook_signature
from App.database import db
from Services.incident_preparer import IncidentContextPreparer
from run_pipeline import process_incident

logger = logging.getLogger("servicenow_webhook")
router = APIRouter()
preparer = IncidentContextPreparer(max_chars=4000)


async def run_ai_pipeline(incident_context, sys_id: str):
    """Background task: retrieval, answer/escalation, console trace."""
    try:
        # process_incident is blocking (model + network), so keep it off the event loop
        await asyncio.to_thread(process_incident, incident_context)
        await db.update_event_status(sys_id, "completed")
    except Exception:
        logger.exception("AI pipeline failed", extra={"sys_id": sys_id})
        try:
            await db.update_event_status(sys_id, "failed")
        except Exception:
            logger.exception("Failed to update incident webhook status")


@router.post("/api/webhook", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(verify_webhook_signature)])
async def receive_incident_webhook(payload: IncidentPayload, background_tasks: BackgroundTasks):
    logger.info(
        "Received incident webhook",
        extra={"incident_number": payload.number, "sys_id": payload.sys_id},
    )

    event_recorded = False
    try:
        # 1. Deduplication Check
        is_new_event = await db.record_event(payload.sys_id)
        if not is_new_event:
            logger.warning(
                "Duplicate incident webhook ignored",
                extra={"incident_number": payload.number, "sys_id": payload.sys_id},
            )
            return {"status": "duplicate_ignored", "number": payload.number}

        event_recorded = True

        # 2. Run the payload through the security firewall
        incident_context = preparer.process_payload(
            sys_id=payload.sys_id,
            number=payload.number,
            short_desc=payload.short_description or "",
            desc=payload.description or "",
        )

        # 3. Secure logging (no raw payload, to avoid PII in logs)
        logger.info(
            "Guardrails applied successfully. Payload sanitized.",
            extra={
                "incident_number": incident_context.original_number,
                "is_safe": incident_context.is_safe,
                "extracted_tags": incident_context.extracted_tags,
                "truncated_length": len(incident_context.truncated_description),
            },
        )
        logger.info(
            "Guardrails applied | %s | safe=%s | tags=%s | desc_len=%d",
            incident_context.original_number,
            incident_context.is_safe,
            incident_context.extracted_tags,
            len(incident_context.truncated_description),
        )
        # 4. Short-circuit on malicious payloads
        if not incident_context.is_safe:
            logger.warning(
                f"PROMPT INJECTION BLOCKED for incident {payload.number}.",
                extra={"sys_id": payload.sys_id},
            )
            await db.update_event_status(payload.sys_id, "flagged_malicious")
            return {
                "status": "rejected",
                "number": payload.number,
                "message": "Payload rejected due to security policy.",
            }

        # 5. Hand off to the AI pipeline; the 202 goes back before it runs
        background_tasks.add_task(run_ai_pipeline, incident_context, payload.sys_id)

    except Exception as e:
        if event_recorded:
            try:
                await db.update_event_status(payload.sys_id, "failed")
            except Exception:
                logger.exception("Failed to update incident webhook status")
        logger.exception("Failed to process incident webhook")
        raise HTTPException(status_code=500, detail="Internal database error processing event.") from e

    return {
        "status": "accepted",
        "number": payload.number,
        "sys_id": payload.sys_id,
        "message": "Event sanitized and queued for AI processing.",
    }