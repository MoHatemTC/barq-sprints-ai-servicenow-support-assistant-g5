import asyncio

from Services.KB_ingestion_service import KBIngestionService


async def main():

    ingestion = KBIngestionService()

    article = {
        "article_id": "KB0010045",
        "title": "Application Won't Launch or Install - Updated",
        "text": """
        Application Won't Launch or Install

        Restart the application first.

        Check whether the application has pending updates.

        Reinstall the application if the issue continues.

        Contact IT support if the application still does not launch.
        """,
        "workflow_state": "published",
        "category": "IT"
    }

    result = await ingestion.update_article(
        article
    )

    print("Update result:")
    print(result)


asyncio.run(main())