import logging
from typing import Set
from fastapi import APIRouter, status
# Import the schema your teammates already built
from Schema.webhook_schema import IncidentPayload
logger = logging.getLogger("servicenow_webhook")

# Use APIRouter instead of FastAPI()
router = APIRouter()

# In-memory deduplication registry (stores seen sys_id entries)
processed_incident_ids: Set[str] = set()

#  Health check endpoint (verifies server is up)
@router.get("/health")
def health_check():
    return {"status": "healthy", "service": "servicenow-webhook"}

# 3. Primary Webhook Endpoint
@router.post("/api/webhook", status_code=status.HTTP_202_ACCEPTED)
async def receive_incident_webhook(payload: IncidentPayload):
    logger.info("================ NEW INCOMING PAYLOAD ================")
    logger.info(f"Incident Number   : {payload.number}")
    logger.info(f"System ID         : {payload.sys_id}")
    logger.info(f"Short Description : {payload.short_description}")
    logger.info(f"Description       : {payload.description}")
    logger.info("======================================================")

    # Deduplication check: drop duplicate deliveries
    if payload.sys_id in processed_incident_ids:
        logger.warning(f"Duplicate event ignored for Incident: {payload.number} ({payload.sys_id})")
        return {
            "status": "duplicate_ignored",
            "number": payload.number,
            "message": "Payload already received and processed."
        }

    # Register the sys_id to prevent re-runs
    processed_incident_ids.add(payload.sys_id)

    # Acknowledge immediately before running any heavy downstream tasks
    return {
        "status": "accepted",
        "number": payload.number,
        "sys_id": payload.sys_id,
        "message": "Event validated and queued successfully."
    }