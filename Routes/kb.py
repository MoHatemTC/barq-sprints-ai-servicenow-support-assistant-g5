from fastapi import APIRouter, Header, HTTPException

from Services.KB_service import KB_services
from Services.KB_ingestion_service import KBIngestionService

from Schema.KB_event_schema import KB_event
from Schema.settings import settings


router = APIRouter(
    prefix="/articles",
    tags=["Articles"]
)


@router.get("/all")
async def get_KB():
    kb_retrieve = KB_services()

    articles = await kb_retrieve.get_articles()

    return {
        "Articles": articles
    }


@router.post("/events")
async def get_KB_event(
    article: KB_event,
    x_api_key: str = Header(...)
):
    # Validate API Key
    if x_api_key != settings.API_SECRET_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )

    ingestion = KBIngestionService()

    normalized_article = {
        "article_id": article.article_id,
        "title": article.short_description,
        "text": article.text,
        "workflow_state": article.workflow_state,
        "category": article.kb_category
    }

    # INSERT
    if article.operation == "insert":

        result = await ingestion.ingest_article(
            normalized_article
        )

        return {
            "message": "Article inserted successfully",
            "operation": "insert",
            "result": result
        }

    # UPDATE
    elif article.operation == "update":

        # RETIRED ARTICLE
        if article.workflow_state == "retired":

            ingestion.qdrant.delete_article(
                article.article_id
            )

            return {
                "message": "Article retired successfully",
                "operation": "update",
                "workflow_state": "retired",
                "article_id": article.article_id
            }

        # NORMAL UPDATE
        result = await ingestion.update_article(
            normalized_article
        )

        return {
            "message": "Article updated successfully",
            "operation": "update",
            "result": result
        }

    # DELETE
    elif article.operation == "delete":

        ingestion.qdrant.delete_article(
            article.article_id
        )

        return {
            "message": "Article deleted successfully",
            "operation": "delete",
            "article_id": article.article_id
        }