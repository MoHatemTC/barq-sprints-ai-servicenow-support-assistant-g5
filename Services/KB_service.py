import logging

from Clients.serviceNow_clients import serviceNow_client
from Schemas.KB_schema import ServiceNowKBArticle
from pydantic import ValidationError

logger = logging.getLogger("servicenow_webhook.kb_service")

class KB_services:
    async def get_articles(self):
        response = await serviceNow_client.KB_connection()

        articles_data = response.get('result', [])
        if not articles_data:
            logger.info("No published knowledge base articles were returned.")
            return []

        validated_articles = []
        for item in articles_data:
            try:
                article = ServiceNowKBArticle(**item)
                validated_articles.append(article)
                logger.debug("Validated knowledge base article", extra={"article_number": article.number})
            except ValidationError as e:
                logger.warning(
                    "Knowledge base article failed validation",
                    extra={"article_number": item.get('number', 'Unknown'), "errors": e.errors()},
                )

        return [article.model_dump() for article in validated_articles]