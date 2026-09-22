import asyncio
import httpx

from fastapi import APIRouter, Header, HTTPException, status

from Services.KB_service import KB_services
from Services.KB_ingestion_service import KBIngestionService
from schemas.KB_event_schema import KB_event
from schemas.settings import settings


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


def build_reindex_article(article: dict) -> dict:
    return {
        "article_id": article["article_id"],
        "title": article.get("short_description") or "",
        "text": article.get("text") or "",
        "workflow_state": article.get("workflow_state") or "published",
        "category": article.get("kb_category"),
    }


@router.post("/reindex")
async def reindex_articles(
    x_api_key: str | None = Header(default=None),
):
    if x_api_key != settings.API_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    try:
        articles = await KB_services().get_articles()
        ingestion = KBIngestionService()
        results = await ingestion.ingest_articles(
            [build_reindex_article(article) for article in articles]
        )
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve articles from ServiceNow.",
        )

    return {
        "status": "success",
        "articles": len(results),
        "chunks": sum(result["chunks"] for result in results),
        "vectors": sum(result["vectors"] for result in results),
    }


@router.post("/events")
async def handle_kb_event(
    event: KB_event,
    x_api_key: str | None = Header(default=None)
):

    # Validate API key
    if x_api_key != settings.API_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key."
        )

    ingestion = KBIngestionService()

    operation = event.operation

    # INSERT
    if operation == "insert":

        article = build_ingestion_article(event)

        result = await ingestion.ingest_article(article)

        return {
            "status": "success",
            "operation": "insert",
            "result": result
        }

    # UPDATE
    if operation == "update":

        article = build_ingestion_article(event)

        result = await ingestion.update_article(article)

        return {
            "status": "success",
            "operation": "update",
            "result": result
        }

    # DELETE
    if operation == "delete":

        await asyncio.to_thread(
            ingestion.qdrant.delete_article,
            event.article_id
        )

        return {
            "status": "success",
            "operation": "delete",
            "article_id": event.article_id
        }

    # RETIRE
    if operation == "retire":

        result = await ingestion.retire_article(
            event.article_id
        )

        return {
            "status": "success",
            "operation": "retire",
            "result": result
        }

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported operation: {operation}"
    )