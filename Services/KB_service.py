from Clients.serviceNow_clients import serviceNow_client
from Schema.KB_schema import ServiceNowKBArticle
from pydantic import ValidationError

class KB_services:
    async def get_articles(self):
        print("Fetching articles from ServiceNow...")
        try:
            response = await serviceNow_client.KB_connection()
        except Exception as e:
            print(f"Error fetching articles: {e}")
            return []

        # Assuming ServiceNow returns data in 'result' key
        articles_data = response.get('result', [])
        if not articles_data:
            print("No articles found or unexpected response format.")
            return []

        validated_articles = []
        for item in articles_data:
            try:
                article = ServiceNowKBArticle(**item)
                validated_articles.append(article)
                print(f"✅ Validated Article: [{article.number}] {article.short_description} (State: {article.workflow_state})")
            except ValidationError as e:
                print(f"❌ Validation failed for article {item.get('number', 'Unknown')}:")
                for err in e.errors():
                    print(f"  - {err['loc'][0]}: {err['msg']}")

        return [article.model_dump() for article in validated_articles]