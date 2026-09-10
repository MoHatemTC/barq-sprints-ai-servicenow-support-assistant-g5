from fastapi import APIRouter
from Services.KB_service import KB_services

router = APIRouter(
    prefix = "/articles",
    tags=["Articles"]
)

@router.get("/all")
async def get_KB():
    kb_retrieve = KB_services()
    articles = await kb_retrieve.get_articles()
    return {"Articles" : articles}
