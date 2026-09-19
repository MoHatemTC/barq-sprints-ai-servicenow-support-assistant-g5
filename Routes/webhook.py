import logging
from fastapi import APIRouter, Depends, HTTPException, status
from Schemas.webhook_schema import IncidentPayload
from App.auth import verify_webhook_signature
from App.database import db

logger = logging.getLogger("servicenow_webhook")

router = APIRouter()

@router.post("/api/webhook", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(verify_webhook_signature)])
async def receive_incident_webhook(payload: IncidentPayload):
    logger.info(
        "Received incident webhook",
        extra={"incident_number": payload.number, "sys_id": payload.sys_id},
    )

    event_recorded = False
    try:
        is_new_event = await db.record_event(payload.sys_id)
        if not is_new_event:
            logger.warning(
                "Duplicate incident webhook ignored",
                extra={"incident_number": payload.number, "sys_id": payload.sys_id},
            )
            return {
                "status": "duplicate_ignored",
                "number": payload.number,
                "message": "Payload was already received."
            }
        event_recorded = True

        logger.info(
            "Validated incident webhook",
            extra={
                "incident_number": payload.number,
                "sys_id": payload.sys_id,
                "short_description": payload.short_description,
                "description": payload.description,
            },
        )

        await db.update_event_status(payload.sys_id, "completed")
    except Exception as e:
        if event_recorded:
            try:
                await db.update_event_status(payload.sys_id, "failed")
            except Exception:
                logger.exception(
                    "Failed to update incident webhook status",
                    extra={"incident_number": payload.number, "sys_id": payload.sys_id},
                )
        logger.exception(
            "Failed to process incident webhook",
            extra={"incident_number": payload.number, "sys_id": payload.sys_id},
        )
        raise HTTPException(status_code=500, detail="Internal database error processing event.") from e

    return {
        "status": "accepted",
        "number": payload.number,
        "sys_id": payload.sys_id,
        "message": "Event accepted."
    }