import asyncio

from Services.text_cleaner import clean_html_text
from Services.chunking_service import ChunkingService
from Services.embedding_service import EmbeddingService
from Services.qdrant_service import QdrantService


class KBIngestionService:

    def __init__(self):

        self.chunker = ChunkingService(
            chunk_size=50,
            chunk_overlap=1
        )

        self.embedder = EmbeddingService()

        self.qdrant = QdrantService()

    async def ingest_article(
        self,
        article: dict
    ):

        return await asyncio.to_thread(
            self._ingest_article_sync,
            article
        )

    def _ingest_article_sync(
        self,
        article: dict
    ):

        article_id = article["article_id"]
        title = article["title"]
        text = article["text"]
        workflow_state = article["workflow_state"]
        category = article["category"]

        # 1. Clean HTML
        clean_text = clean_html_text(text)

        # 2. Chunk text
        chunks = self.chunker.chunk_text(
            clean_text
        )

        # 3. Create embeddings
        vectors = self.embedder.embed_chunks(
            chunks
        )

        # 4. Upsert vectors into Qdrant
        self.qdrant.upsert_chunks(
            article_id=article_id,
            title=title,
            category=category,
            workflow_state=workflow_state,
            chunks=chunks,
            vectors=vectors
        )

        return {
            "article_id": article_id,
            "chunks": len(chunks),
            "vectors": len(vectors)
        }

    async def ingest_articles(
        self,
        articles: list[dict]
    ):

        results = []

        for article in articles:

            result = await self.ingest_article(
                article
            )

            results.append(result)

        return results

    async def ingest_articles_async(
        self,
        articles: list[dict],
        batch_size: int = 5
    ):

        results = []

        for start in range(
            0,
            len(articles),
            batch_size
        ):

            batch = articles[
                start:start + batch_size
            ]

            batch_results = await asyncio.gather(
                *[
                    asyncio.to_thread(
                        self._ingest_article_sync,
                        article
                    )
                    for article in batch
                ]
            )

            results.extend(batch_results)

            print(
                f"Processed batch: "
                f"{start + 1}-"
                f"{start + len(batch)}"
            )

        return results

    async def update_article(
        self,
        article: dict
    ):

        article_id = article["article_id"]

        # Remove old chunks first
        await asyncio.to_thread(
            self.qdrant.delete_article,
            article_id
        )

        # Ingest the updated article
        result = await self.ingest_article(
            article
        )

        print(
            f"Article {article_id} "
            f"updated successfully."
        )

        return result

    async def retire_article(
        self,
        article_id: str
    ):

        # Remove all vectors for the retired article
        await asyncio.to_thread(
            self.qdrant.delete_article,
            article_id
        )

        print(
            f"Article {article_id} "
            f"retired successfully."
        )

        return {
            "article_id": article_id,
            "status": "retired"
        }