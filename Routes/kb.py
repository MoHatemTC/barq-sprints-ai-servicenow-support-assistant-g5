import asyncio
import logging

import httpx
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import ValidationError
from schemas.KB_ingestion_schema import KBIngestionPayload

from schemas.KB_event_schema import KB_event
from schemas.settings import settings
from Services.KB_service import KB_services
from Services.shared import get_ingestion_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/articles", tags=["Articles"])


@router.get("/all")
async def get_KB():
    try:
        articles = await KB_services().get_articles()
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve articles from ServiceNow.",
        )
    return {"Articles": articles}


def build_ingestion_article(event: KB_event) -> dict:
    try:
        return KBIngestionPayload(
            article_id=event.article_id,
            title=event.short_description,
            text=event.text or "",
            workflow_state=event.workflow_state,
            category=event.kb_category,
        ).model_dump()
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())


@router.post("/events")
async def handle_kb_event(
    event: KB_event,
    x_api_key: str | None = Header(default=None),
):
    if x_api_key != settings.API_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    ingestion = get_ingestion_service()  # shared: model loaded once, not per request
    operation = event.operation
    logger.info("KB event: %s | %s", operation, event.article_id)

    try:
        if operation == "insert":
            result = await ingestion.ingest_article(build_ingestion_article(event))
            return {"status": "success", "operation": "insert", "result": result}

        if operation == "update":
            result = await ingestion.update_article(build_ingestion_article(event))
            return {"status": "success", "operation": "update", "result": result}

        if operation == "delete":
            await asyncio.to_thread(ingestion.qdrant.delete_article, event.article_id)
            return {"status": "success", "operation": "delete", "article_id": event.article_id}

        if operation == "retire":
            result = await ingestion.retire_article(event.article_id)
            return {"status": "success", "operation": "retire", "result": result}

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported operation: {operation}",
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("KB event failed: %s | %s", operation, event.article_id)
        raise
