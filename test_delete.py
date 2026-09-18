from Services.qdrant_service import QdrantService


qdrant = QdrantService()

article_id = "KB0010045"

before = qdrant.filter_chunks(
    field="article_id",
    value=article_id,
    limit=100,
)

print(f"Before delete: {len(before)} chunks")

qdrant.delete_article(article_id)

after = qdrant.filter_chunks(
    field="article_id",
    value=article_id,
    limit=100,
)

print(f"After delete: {len(after)} chunks")