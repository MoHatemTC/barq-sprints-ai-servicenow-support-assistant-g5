import os
import uuid

from dotenv import load_dotenv

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    FilterSelector,
)


load_dotenv()


import os
import uuid

from dotenv import load_dotenv

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    FilterSelector,
    PayloadSchemaType,
)

load_dotenv()


class QdrantService:

    VECTOR_SIZE = 384  # all-MiniLM-L6-v2

    def __init__(self, collection_name: str | None = None):

        self.collection_name = collection_name or os.getenv(
            "QDRANT_COLLECTION", "kb_articles"
        )

        url = os.getenv("QDRANT_URL")
        api_key = os.getenv("QDRANT_API_KEY")

        if url:
            # Qdrant Cloud (or any remote instance)
            self.client = QdrantClient(url=url, api_key=api_key, timeout=30)
        else:
            # Local fallback (Docker Compose)
            self.client = QdrantClient(
                host=os.getenv("QDRANT_HOST", "localhost"),
                port=int(os.getenv("QDRANT_PORT", "6333")),
                timeout=30,
            )
        self.ensure_collection()

    def ensure_collection(self):
        """Create the collection and payload indexes if they don't exist. Safe to call repeatedly."""

        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
            )
            print(f"Collection '{self.collection_name}' created.")
        else:
            print(f"Collection '{self.collection_name}' already exists.")

        # Indexes are needed for filtering (Task 5) and delete-by-article_id
        for field in ("article_id", "workflow_state", "category"):
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )

    def upsert_chunks(
        self,
        article_id: str,
        title: str,
        category: str,
        workflow_state: str,
        chunks: list[str],
        vectors: list[list[float]],
    ):

        points = []

        for index, (chunk, vector) in enumerate(
            zip(chunks, vectors)
        ):

            # Deterministic UUID.
            # Re-ingesting the same article/chunk
            # produces the same point ID.
            point_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{article_id}_chunk_{index}",
                )
            )

            point = PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "article_id": article_id,
                    "title": title,
                    "category": category,
                    "workflow_state": workflow_state,
                    "chunk_index": index,
                    "text": chunk,
                },
            )

            points.append(point)

        if points:

            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )

        print(
            f"Upserted {len(points)} chunks "
            f"for article {article_id}."
        )

    def filter_chunks(
        self,
        field: str,
        value: str,
        limit: int = 10,
    ):

        result = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key=field,
                        match=MatchValue(value=value),
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        points, next_page_offset = result

        return points

    def delete_article(
        self,
        article_id: str,
    ):

        self.client.delete(
            collection_name=self.collection_name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="article_id",
                            match=MatchValue(
                                value=article_id
                            ),
                        )
                    ]
                )
            ),
        )

        print(
            f"Deleted all chunks for article "
            f"{article_id}."
        )