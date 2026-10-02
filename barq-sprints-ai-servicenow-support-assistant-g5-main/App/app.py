import asyncio
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from App.database import db
from Routes import webhook
from Routes.kb import router as kb_router
from Services.KB_ingestion_service import reindex_all
from Services.shared import get_embedder, get_qdrant

logger = logging.getLogger("servicenow_webhook.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()

    # Load the model and Qdrant client once, so the first incident isn't slow.
    await asyncio.to_thread(get_embedder)
    qdrant = await asyncio.to_thread(get_qdrant)

    # Empty collection (fresh setup or new EMBEDDING_MODEL_NAME) -> rebuild.
    try:
        if await asyncio.to_thread(qdrant.count_points) == 0:
            logger.info("Collection '%s' is empty, reindexing from ServiceNow.", qdrant.collection_name)
            logger.info("Startup reindex done: %s", await reindex_all())
    except Exception:
        # Don't block the API from starting; KB events and reindex.py still work.
        logger.exception("Startup reindex failed. Run `python reindex.py` manually.")

    yield
    await db.disconnect()


app = FastAPI(
    title="AI ServiceNow Support Assistant API",
    version="1.0.0",
    description="Backend service for processing ServiceNow incident webhooks and running AI retrieval workflows.",
    lifespan=lifespan,
)

app.include_router(webhook.router)
app.include_router(kb_router)
