import logging
from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.webhook_schema import IncidentPayload
from app.core.auth import verify_webhook_signature
from app.core.database import db

logger = logging.getLogger("servicenow_webhook")

router = APIRouter()

@router.post("/api/webhook", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(verify_webhook_signature)])
async def receive_incident_webhook(payload: IncidentPayload):
    logger.info(
        "Received incident webhook",
        extra={"incident_number": payload.number, "sys_id": payload.sys_id},
    )

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
    except Exception as e:
        logger.exception(
            "Failed to record incident webhook",
            extra={"incident_number": payload.number, "sys_id": payload.sys_id},
        )
        raise HTTPException(status_code=500, detail="Internal database error processing event.")

    logger.info(
        "Validated incident webhook",
        extra={
            "incident_number": payload.number,
            "sys_id": payload.sys_id,
            "short_description": payload.short_description,
            "description": payload.description,
        },
    )

    return {
        "status": "accepted",
        "number": payload.number,
        "sys_id": payload.sys_id,
        "message": "Event accepted."
    }