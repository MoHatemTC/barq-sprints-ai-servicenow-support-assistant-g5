from Services.qdrant_service import QdrantService


qdrant = QdrantService()

qdrant.create_collection()

chunks = [
    "The application does not launch after installation.",
    "Check whether the required dependencies are installed correctly.",
    "Restart the application and reinstall it if the problem continues."
]

vectors = [
    [0.1] * 384,
    [0.2] * 384,
    [0.3] * 384
]

qdrant.upsert_chunks(
    article_id="KB0010045",
    title="Application Won't Launch or Install",
    category="IT",
    workflow_state="published",
    chunks=chunks,
    vectors=vectors
)