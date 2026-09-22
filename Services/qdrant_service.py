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

VECTOR_SIZE = 768
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "kb_articles_bge_base")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")


class QdrantService:

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        collection_name: str = COLLECTION_NAME,
    ):

        self.collection_name = collection_name

        configured_host = host or os.getenv("QDRANT_HOST")
        configured_port = port or os.getenv("QDRANT_PORT")
        if configured_host and configured_port:
            self.client = QdrantClient(
                host=configured_host,
                port=int(configured_port),
            )
        else:
            self.client = QdrantClient(
                url=QDRANT_URL or "http://localhost:6333",
                api_key=QDRANT_API_KEY,
                headers={"ngrok-skip-browser-warning": "true"},
            )

    def create_collection(self):

        collections = self.client.get_collections()

        existing_collections = [
            collection.name
            for collection in collections.collections
        ]

        if self.collection_name not in existing_collections:

            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
            )

            print(
                f"Collection '{self.collection_name}' "
                f"created successfully."
            )

        else:

            collection_info = self.client.get_collection(
                collection_name=self.collection_name
            )
            vectors = collection_info.config.params.vectors
            if isinstance(vectors, dict) or vectors.size != VECTOR_SIZE:
                raise ValueError(
                    f"Collection '{self.collection_name}' must use "
                    f"unnamed vectors with size {VECTOR_SIZE}. "
                    "Recreate the collection before reindexing."
                )

            print(
                f"Collection '{self.collection_name}' "
                f"already exists."
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

        self.create_collection()

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