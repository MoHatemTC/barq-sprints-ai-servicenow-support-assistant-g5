import os
import uuid
import re

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
from Services.embedding_service import EMBEDDING_MODEL_NAME

load_dotenv()

# Must match the embedding model: bge-base-en-v1.5 = 768 dims.
# EMBEDDING_MODEL_NAME comes from embedding_service (single source of truth).
# The collection name is derived from it, so a model change = new empty
# collection = automatic reindex at startup.
VECTOR_SIZE = int(os.getenv("EMBEDDING_VECTOR_SIZE", "768"))
_model_slug = re.sub(r"[^a-z0-9]+", "_", EMBEDDING_MODEL_NAME.lower()).strip("_")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_PREFIX", "kb") + "_" + _model_slug  # -> kb_baai_bge_base_en_v1_5
INDEXED_FIELDS = ("article_id", "workflow_state", "category")


class QdrantService:

    def __init__(
        self,
        collection_name: str | None = None,
        url: str | None = None,
        host: str | None = None,
        port: int | None = None,
    ):
        self.collection_name = collection_name or COLLECTION_NAME

        url = url or os.getenv("QDRANT_URL")
        api_key = os.getenv("QDRANT_API_KEY")

        if url:
            # Qdrant Cloud or any remote instance
            self.client = QdrantClient(url=url, api_key=api_key, timeout=30)
        else:
            # Local fallback (Docker Compose service name or localhost)
            self.client = QdrantClient(
                host=host or os.getenv("QDRANT_HOST", "localhost"),
                port=int(port or os.getenv("QDRANT_PORT", "6333")),
                timeout=30,
            )

        self.ensure_collection()

    # ------------------------------------------------------------------ #
    # Collection setup
    # ------------------------------------------------------------------ #
    def ensure_collection(self):
        """Create the collection + payload indexes if missing,
        and refuse to run against a collection with the wrong vector size.
        Safe to call repeatedly."""

        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
            )
            print(f"Collection '{self.collection_name}' created.")
        else:
            info = self.client.get_collection(self.collection_name)
            vectors = info.config.params.vectors
            if isinstance(vectors, dict) or vectors.size != VECTOR_SIZE:
                raise ValueError(
                    f"Collection '{self.collection_name}' must use unnamed "
                    f"vectors of size {VECTOR_SIZE}. Check EMBEDDING_VECTOR_SIZE "
                    "matches EMBEDDING_MODEL_NAME, or delete the collection "
                    "and restart / run `python reindex.py`."
                )
            print(f"Collection '{self.collection_name}' already exists.")

        # Needed for published-only filtering (Task 5) and delete-by-article_id
        for field in INDEXED_FIELDS:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )

    # Backward-compatible name used by the team's code
    create_collection = ensure_collection

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #
    def upsert_chunks(
        self,
        article_id: str,
        title: str,
        category: str,
        workflow_state: str,
        chunks: list[str],
        vectors: list[list[float]],
    ):
        if len(chunks) != len(vectors):
            raise ValueError(
                f"Chunk/vector count mismatch for {article_id}: "
                f"{len(chunks)} chunks vs {len(vectors)} vectors"
            )

        points = []
        for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
            # Deterministic ID: same article + chunk index -> same point
            point_id = str(
                uuid.uuid5(uuid.NAMESPACE_URL, f"{article_id}_chunk_{index}")
            )
            points.append(
                PointStruct(
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
            )

        if points:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )

        print(f"Upserted {len(points)} chunks for article {article_id}.")

    def delete_article(self, article_id: str):
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="article_id",
                            match=MatchValue(value=article_id),
                        )
                    ]
                )
            ),
        )
        print(f"Deleted all chunks for article {article_id}.")

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    def filter_chunks(self, field: str, value: str, limit: int = 10):
        points, _next_offset = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key=field, match=MatchValue(value=value))
                ]
            ),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return points

    def count_points(self) -> int:
        """Used by the startup check to decide whether a reindex is needed."""
        return self.client.count(
            collection_name=self.collection_name, exact=True
        ).count