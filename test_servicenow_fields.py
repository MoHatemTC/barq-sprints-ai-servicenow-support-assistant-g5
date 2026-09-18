import asyncio
from Clients.serviceNow_clients import serviceNow_client


async def main():

    data = await serviceNow_client.KB_connection()

    articles = data.get("result", [])

    print(f"Number of articles: {len(articles)}")

    if articles:

        article = articles[0]

        print("\nFirst article fields:")
        print("=" * 50)

        for key, value in article.items():
            print(f"{key}: {value}")

        print("\narticle_id:")
        print(article.get("article_id"))

        print("\nnumber:")
        print(article.get("number"))

        print("\nsys_id:")
        print(article.get("sys_id"))


asyncio.run(main())