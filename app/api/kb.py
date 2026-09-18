import httpx
from fastapi import APIRouter, HTTPException, status
from app.services.KB_service import KB_services

router = APIRouter(
    prefix = "/articles",
    tags=["Articles"]
)

@router.get("")
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