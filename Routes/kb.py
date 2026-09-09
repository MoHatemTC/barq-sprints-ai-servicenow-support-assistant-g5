from fastapi import APIRouter
from Services.KB_service import KB_services

router = APIRouter(
    prefix = "/articles",
    tags=["Articles"]
)

@router.get("/all")
async def get_KB():
    kb_retrieve = KB_services()
    return{"Articles" : kb_retrieve.get_articles()}
