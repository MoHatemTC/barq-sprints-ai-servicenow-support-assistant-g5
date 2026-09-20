import asyncio

from dotenv import load_dotenv

load_dotenv()

from Services.KB_service import KB_services
from Services.KB_ingestion_service import KBIngestionService


async def main():
    ingestion = KBIngestionService()

    articles = await KB_services().get_articles()
    print(f"Fetched {len(articles)} published articles from ServiceNow.")

    total_chunks = 0

    for a in articles:
        if not a.get("text"):
            print(f"Skipping {a['article_id']} (no text).")
            continue

        payload = {
            "article_id": a["article_id"],
            "title": a["short_description"],
            "text": a["text"],
            "workflow_state": a["workflow_state"],
            "category": a.get("kb_category") or "Uncategorized",
        }

        # delete old chunks first, then ingest, so re-runs leave no stale chunks
        result = await ingestion.update_article(payload)
        total_chunks += result["chunks"]

    print(f"Done. {total_chunks} chunks indexed.")


if __name__ == "__main__":
    asyncio.run(main())