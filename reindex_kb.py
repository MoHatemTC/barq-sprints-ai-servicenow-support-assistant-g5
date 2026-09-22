import asyncio

from Services.KB_ingestion_service import KBIngestionService
from Services.KB_service import KB_services


def to_ingestion_article(article: dict) -> dict:
    return {
        "article_id": article["article_id"],
        "title": article.get("short_description") or "",
        "text": article.get("text") or "",
        "workflow_state": article.get("workflow_state") or "published",
        "category": article.get("kb_category"),
    }


async def main() -> None:
    source = KB_services()
    articles = await source.get_articles()
    ingestion_articles = [
        to_ingestion_article(article)
        for article in articles
        if article.get("text")
    ]

    print(f"Fetched {len(ingestion_articles)} articles for reindexing.")
    await KBIngestionService().ingest_articles(ingestion_articles)
    print("Re-indexing completed.")


if __name__ == "__main__":
    asyncio.run(main())
