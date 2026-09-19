from fastapi import APIRouter, Header, HTTPException

from Services.KB_service import KB_services
from schemas.KB_event_schema import KB_event
from schemas.settings import settings


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
def get_KB_event(
    article: KB_event,
    x_api_key: str = Header(...)
):
    # Validate API Key
    if x_api_key != settings.API_SECRET_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )

    print("========== KB EVENT ==========")
    print(f"Article ID: {article.article_id}")
    print(f"Sys ID: {article.sys_id}")
    print(f"Operation: {article.operation}")
    print(f"Workflow State: {article.workflow_state}")
    print(f"Short Description: {article.short_description}")
    print(f"Author: {article.author}")
    print(f"KB Category: {article.kb_category}")
    print(f"Text: {article.text}")
    print("==============================")

    return {
        "message": "Event received"
    }
