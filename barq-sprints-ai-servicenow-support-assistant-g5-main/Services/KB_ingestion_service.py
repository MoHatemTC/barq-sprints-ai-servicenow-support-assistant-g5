import asyncio
import logging
import os

from Services.chunking_service import ChunkingService
from Services.KB_service import KB_services
from Services.text_cleaner import clean_html_text

logger = logging.getLogger(__name__)

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "40"))       # words per chunk
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "1"))  # sentences, keep at 1


class KBIngestionService:

    def __init__(self, embedder=None, qdrant=None):
        # Shared instances: the model is loaded once per process.
        from Services.shared import get_embedder, get_qdrant

        self.chunker = ChunkingService(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )
        self.embedder = embedder or get_embedder()
        self.qdrant = qdrant or get_qdrant()

    async def ingest_article(self, article: dict):
        return await asyncio.to_thread(self._ingest_article_sync, article)

    def _ingest_article_sync(self, article: dict):
        article_id = article["article_id"]
        title = article["title"]

        # 1. Clean HTML  2. Chunk
        chunks = self.chunker.chunk_text(clean_html_text(article["text"]))

        # 3. Embed with the title as context
        vectors = self.embedder.embed_chunks(
            [f"{title}\n\n{chunk}" for chunk in chunks]
        )

        # 4. Replace old chunks (handles articles that got shorter)
        self.qdrant.delete_article(article_id)
        self.qdrant.upsert_chunks(
            article_id=article_id,
            title=title,
            category=article["category"],
            workflow_state=article["workflow_state"],
            chunks=chunks,
            vectors=vectors,
        )

        return {"article_id": article_id, "chunks": len(chunks), "vectors": len(vectors)}

    async def ingest_articles(self, articles: list[dict]):
        return [await self.ingest_article(article) for article in articles]

    async def update_article(self, article: dict):
        # ingest_article already deletes old chunks before upserting
        result = await self.ingest_article(article)
        logger.info("Article %s updated.", article["article_id"])
        return result

    async def retire_article(self, article_id: str):
        await asyncio.to_thread(self.qdrant.delete_article, article_id)
        logger.info("Article %s retired.", article_id)
        return {"article_id": article_id, "status": "retired"}


# ---------------------------------------------------------------------- #
# Full rebuild from ServiceNow (used by reindex.py and the startup check)
# ---------------------------------------------------------------------- #
def to_ingestion_article(article: dict) -> dict:
    """Map a ServiceNow KB record to the ingestion format.

    article_id = KB number (e.g. KB0010001), NOT the 32-char internal id:
    it is what the KB Business Rule sends on insert/update/retire, and the
    format the citation validator in response_formatter expects.
    """
    return {
        "article_id": article.get("number") or article["article_id"],
        "title": article.get("short_description") or "",
        "text": article.get("text") or "",
        "workflow_state": article.get("workflow_state") or "published",
        "category": article.get("kb_category"),
    }


async def reindex_all() -> dict:
    articles = await KB_services().get_articles()
    payload = [to_ingestion_article(a) for a in articles if a.get("text")]
    logger.info("Reindexing %d published articles from ServiceNow.", len(payload))

    from Services.shared import get_ingestion_service
    results = await get_ingestion_service().ingest_articles(payload)

    return {
        "articles": len(results),
        "chunks": sum(r["chunks"] for r in results),
        "vectors": sum(r["vectors"] for r in results),
    }
