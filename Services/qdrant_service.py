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


class QdrantService:

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        collection_name: str = "kb_articles",
    ):

        self.collection_name = collection_name

        # Use environment variables when available.
        # Defaults keep local testing working.
        qdrant_host = host or os.getenv(
            "QDRANT_HOST",
            "localhost"
        )

        qdrant_port = port or int(
            os.getenv(
                "QDRANT_PORT",
                "6333"
            )
        )

        self.client = QdrantClient(
            host=qdrant_host,
            port=qdrant_port,
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
                    size=384,
                    distance=Distance.COSINE,
                ),
            )

            print(
                f"Collection '{self.collection_name}' "
                f"created successfully."
            )

        else:

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