import asyncio

from Clients.serviceNow_clients import serviceNow_client
from Services.KB_ingestion_service import KBIngestionService


async def main():

    client = serviceNow_client()

    data = await client.KB_connection()

    articles = data.get("result", [])

    print(f"Found {len(articles)} articles.")

    normalized_articles = []

    for article in articles:

        normalized_article = {
            "article_id": article["number"]["value"],
            "title": article["short_description"]["value"],
            "text": article["text"]["value"],
            "workflow_state": article["workflow_state"]["value"],
            "category": article["kb_category"]["display_value"]
        }

        normalized_articles.append(normalized_article)

    ingestion = KBIngestionService()

    results = await ingestion.ingest_articles_async(
       normalized_articles,
       batch_size=5
    )
    

    print("\nIngestion completed.")

    for result in results:
        print(result)


asyncio.run(main())