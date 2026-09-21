import asyncio
import httpx
import logging

from fastapi import APIRouter, Header, HTTPException, status

from Services.KB_service import KB_services
from Services.KB_ingestion_service import KBIngestionService
from Schemas.KB_event_schema import KB_event
from Schemas.settings import settings


router = APIRouter(
    prefix="/articles",
    tags=["Articles"]
)


@router.get("/all")
async def get_KB():

    kb_retrieve = KB_services()

    try:
        articles = await kb_retrieve.get_articles()

    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve articles from ServiceNow."
        )

    return {
        "Articles": articles
    }


def build_ingestion_article(event: KB_event) -> dict:
    """
    Convert the ServiceNow KB event format
    into the format expected by KBIngestionService.
    """

    return {
        "article_id": event.article_id,
        "title": event.short_description,
        "text": event.text,
        "workflow_state": event.workflow_state,
        "category": event.kb_category,
    }


logger = logging.getLogger(__name__)


@router.post("/events")
async def handle_kb_event(
    event: KB_event,
    x_api_key: str | None = Header(default=None)
):

    logger.info("========== KB EVENT RECEIVED ==========")

    logger.info(
        "Operation: %s | Article ID: %s",
        event.operation,
        event.article_id
    )

    logger.info(
        "Workflow State: %s | Version: %s",
        event.workflow_state,
        event.version
    )

    logger.info(
        "Title: %s",
        event.short_description
    )

    logger.info(
        "Category: %s | Author: %s",
        event.kb_category,
        event.author
    )

    logger.info(
        "Text length: %s",
        len(event.text or "")
    )

    # Validate API key
    if x_api_key != settings.API_SECRET_KEY:

        logger.warning(
            "Invalid API key for Article ID: %s",
            event.article_id
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key."
        )

    logger.info(
        "API key validation successful for Article ID: %s",
        event.article_id
    )

    ingestion = KBIngestionService()

    operation = event.operation

    try:

        # =========================
        # INSERT
        # =========================

        if operation == "insert":

            logger.info(
                "[INSERT] Starting ingestion for Article: %s",
                event.article_id
            )

            article = build_ingestion_article(event)

            logger.info(
                "[INSERT] Article built successfully | "
                "Title: %s | Text length: %s",
                article["title"],
                len(article["text"] or "")
            )

            result = await ingestion.ingest_article(article)

            logger.info(
                "[INSERT] Completed | Article: %s | "
                "Chunks: %s | Vectors: %s",
                event.article_id,
                result["chunks"],
                result["vectors"]
            )

            return {
                "status": "success",
                "operation": "insert",
                "result": result
            }

        # =========================
        # UPDATE
        # =========================

        if operation == "update":

            logger.info(
                "[UPDATE] Starting update for Article: %s",
                event.article_id
            )

            article = build_ingestion_article(event)

            logger.info(
                "[UPDATE] New article data built | "
                "Title: %s | Text length: %s | Version: %s",
                article["title"],
                len(article["text"] or ""),
                article.get("version")
            )

            logger.info(
                "[UPDATE] Calling delete_article for old vectors | "
                "Article: %s",
                event.article_id
            )

            result = await ingestion.update_article(article)

            logger.info(
                "[UPDATE] Completed successfully | "
                "Article: %s | Chunks: %s | Vectors: %s",
                event.article_id,
                result["chunks"],
                result["vectors"]
            )

            return {
                "status": "success",
                "operation": "update",
                "result": result
            }

        # =========================
        # DELETE
        # =========================

        if operation == "delete":

            logger.info(
                "[DELETE] Deleting vectors for Article: %s",
                event.article_id
            )

            await asyncio.to_thread(
                ingestion.qdrant.delete_article,
                event.article_id
            )

            logger.info(
                "[DELETE] Completed successfully | Article: %s",
                event.article_id
            )

            return {
                "status": "success",
                "operation": "delete",
                "article_id": event.article_id
            }

        # =========================
        # RETIRE
        # =========================

        if operation == "retire":

            logger.info(
                "[RETIRE] Removing vectors for Article: %s",
                event.article_id
            )

            result = await ingestion.retire_article(
                event.article_id
            )

            logger.info(
                "[RETIRE] Completed successfully | Article: %s",
                event.article_id
            )

            return {
                "status": "success",
                "operation": "retire",
                "result": result
            }

        logger.warning(
            "Unsupported operation received: %s",
            operation
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported operation: {operation}"
        )

    except Exception:

        logger.exception(
            "KB event processing failed | "
            "Operation: %s | Article: %s",
            operation,
            event.article_id
        )

        raise