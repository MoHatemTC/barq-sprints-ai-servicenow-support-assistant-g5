import logging
from fastapi import APIRouter, Depends, HTTPException, status
from Schemas.webhook_schema import IncidentPayload
from Schemas.incident_worker import WorkerPayload
from App.auth import verify_webhook_signature
from App.database import db
from Services.incident_preparer import IncidentContextPreparer
from Worker.tasks import process_incident_worker
import uuid
from datetime import datetime , timezone

logger = logging.getLogger("servicenow_webhook")
router = APIRouter()

@router.post("/api/webhook", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(verify_webhook_signature)])
async def receive_incident_webhook(payload: IncidentPayload):
    logger.info(
        "Received incident webhook",
        extra={"incident_number": payload.number, "sys_id": payload.sys_id},
    )

    event_recorded = False
    event_id = str(uuid.uuid4())
    received_at = datetime.now(timezone.utc)
    try:
        # Record the event in the database.
        # sys_id is used to prevent duplicate processing of the same incident.
        is_new_event = await db.record_event(event_id , payload.sys_id , payload.number , received_at)
        if not is_new_event:
            logger.warning(
                "Duplicate incident webhook ignored",
                extra={"incident_number": payload.number, "sys_id": payload.sys_id},
            )
            return {"status": "duplicate_ignored", "number": payload.number}

        event_recorded = True
            
        #Celery Task
        worker_context = WorkerPayload(
            event_id=event_id,
            sys_id=payload.sys_id,
            number=payload.number,
            received_at=received_at
        )
        
        incident_serialization = worker_context.model_dump(mode="json")
        process_incident_worker.delay(incident_serialization)
        

    except Exception as e:
        if event_recorded:
            try:
                await db.update_event_status(event_id , "failed")
            except Exception:
                logger.exception("Failed to update incident webhook status")
        logger.exception("Failed to process incident webhook")
        raise HTTPException(status_code=500, detail="Internal database error processing event.") from e

    return {
        "status": "accepted",
        "number": payload.number,
        "sys_id": payload.sys_id,
        "message": "Event accepted and queued for AI processing.",
    }