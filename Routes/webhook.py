import logging
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from schemas.webhook_schema import IncidentPayload
from core.auth import verify_webhook_signature
from core.database import db
from Routes.incident_preparer import IncidentContextPreparer

# Import  Gemini processing function
# from core.pipeline import process_incident_with_llm 

logger = logging.getLogger("servicenow_webhook")
router = APIRouter()
preparer = IncidentContextPreparer(max_chars=4000)

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
        safe_short_desc = payload.short_description or ""
        safe_desc = payload.description or ""
        
        incident_context = preparer.process_payload(
            sys_id=payload.sys_id,
            number=payload.number,
            short_desc=safe_short_desc,
            desc=safe_desc
        )

        # 3. SECURE LOGGING: Log the schema output (Deliverable Requirement)
        # We do not log the raw payload here to prevent PII leakage in server logs
        logger.info(
            "Guardrails applied successfully. Payload sanitized.",
            extra={
                "incident_number": incident_context.original_number,
                "is_safe": incident_context.is_safe,
                "extracted_tags": incident_context.extracted_tags,
                "truncated_length": len(incident_context.truncated_description),
            },
        )

        # 4. TRAFFIC CONTROL: Short-circuit on malicious payloads
        if not incident_context.is_safe:
            logger.warning(
                f" PROMPT INJECTION BLOCKED for incident {payload.number}.",
                extra={"sys_id": payload.sys_id}
            )
            await db.update_event_status(payload.sys_id, "flagged_malicious")
            
            return {
                "status": "rejected",
                "number": payload.number,
                "message": "Payload rejected due to security policy."
            }
              #Next phase
        # 5. HANDOFF: Queue Ibrahim's agent with this new cleaned  data
        # background_tasks.add_task(Ibrahim's Agent, incident_context)

        await db.update_event_status(payload.sys_id, "completed")
        
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
        "message": "Event sanitized and queued for AI processing."
    }