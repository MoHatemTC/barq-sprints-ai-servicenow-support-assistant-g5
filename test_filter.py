from Services.qdrant_service import QdrantService


qdrant = QdrantService()

results = qdrant.filter_chunks(
    field="category",
    value="IT",
)

print(f"Found {len(results)} points.")

for point in results:
    print(
        point.id,
        point.payload
    )