import logging
from fastapi import APIRouter, Depends, HTTPException, status
from App.auth import verify_webhook_signature
from App.resolved_incident_cache import (
    ResolvedIncidentCache,
    generate_cache_key,
)
from Schemas.resolution_schema import ResolvedIncidentPayload
from Services.incident_preparer import IncidentContextPreparer

logger = logging.getLogger("servicenow_webhook.resolution")
router = APIRouter()
preparer = IncidentContextPreparer(max_chars=4000)


@router.post(
    "/api/incident-resolved",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_webhook_signature)],
)
async def receive_resolved_incident(payload: ResolvedIncidentPayload):
    logger.info(
        "Received resolved incident webhook",
        extra={"sys_id": payload.sys_id, "number": payload.number},
    )

    # 1. Not Solved check -> Never cache
    if payload.close_code.startswith("Not Solved"):
        logger.info(
            "Incident close_code is Not Solved. Skipping cache.",
            extra={"sys_id": payload.sys_id, "close_code": payload.close_code},
        )
        return {
            "status": "accepted",
            "cached": False,
            "reason": "incident_not_solved",
        }

    # 2. Run resolution content through security guardrails
    incident_context = preparer.process_payload(
        sys_id=payload.sys_id,
        number=payload.number or "INC0000000",
        short_desc=payload.short_description or "",
        desc=payload.close_notes,
    )

    if not incident_context.is_safe:
        logger.warning(
            "Security guardrail rejected resolution content",
            extra={"sys_id": payload.sys_id},
        )
        return {
            "status": "rejected",
            "cached": False,
            "reason": "unsafe_content",
            "message": "Payload rejected due to security policy.",
        }

    # 3. Generate SHA-256 exact-match Redis key
    cache_key = generate_cache_key(
        payload.short_description,
        payload.description,
    )

    # 4. Construct verified resolution payload
    cache_value = {
        "sys_id": payload.sys_id,
        "number": payload.number,
        "short_description": payload.short_description or "",
        "description": payload.description or "",
        "close_code": payload.close_code,
        "close_notes": payload.close_notes,
        "resolved_by": payload.resolved_by,
        "resolved_at": payload.resolved_at,
        "ai_confidence": payload.ai_confidence,
        "ai_suggested_response": payload.ai_suggested_response,
        "source": "servicenow",
        "verified": True,
    }

    # 5. Store / Upsert in Redis
    try:
        ResolvedIncidentCache.set_cached_resolution(cache_key, cache_value)
        logger.info(
            "Resolved incident %s (sys_id: %s) successfully cached in Redis with key %s",
            payload.number or payload.sys_id,
            payload.sys_id,
            cache_key,
        )
        try:
            from utils.console_tracer import print_cache_store_trace
            print_cache_store_trace(
                number=payload.number,
                sys_id=payload.sys_id,
                cache_key=cache_key,
                close_code=payload.close_code,
                close_notes=payload.close_notes,
            )
        except Exception as t_exc:
            logger.debug("Console trace print warning: %s", t_exc)
    except Exception as exc:
        logger.error(
            "Failed to write resolved incident to Redis: %s",
            exc,
            extra={"sys_id": payload.sys_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Redis storage error.",
        ) from exc

    return {
        "status": "accepted",
        "cached": True,
        "sys_id": payload.sys_id,
        "number": payload.number,
    }
