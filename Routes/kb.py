import httpx
from fastapi import APIRouter, Header, HTTPException

from services.KB_service import KB_services
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
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge base service is unavailable.",
        )
    return {"Articles" : articles}