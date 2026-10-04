import math
import os
import re
import threading
import time
import uuid
from collections import Counter

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

# BGE-M3 and bge-large-en-v1.5 both produce 1024-dimensional dense vectors.
# EMBEDDING_MODEL_NAME comes from embedding_service (single source of truth).
# The collection name is derived from it, so a model change = new empty
# collection = automatic reindex at startup.
VECTOR_SIZE = int(os.getenv("EMBEDDING_VECTOR_SIZE", "1024"))
_model_slug = re.sub(r"[^a-z0-9]+", "_", EMBEDDING_MODEL_NAME.lower()).strip("_")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_PREFIX", "kb") + "_" + _model_slug  # -> kb_baai_bge_m3
INDEXED_FIELDS = ("article_id", "workflow_state", "category")
BM25_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
BM25_CACHE_TTL_SECONDS = 60


class QdrantService:

    def __init__(
        self,
        collection_name: str | None = None,
        url: str | None = None,
        host: str | None = None,
        port: int | None = None,
    ):
        self.collection_name = collection_name or COLLECTION_NAME
        self._bm25_cache: tuple[float, list[tuple[object, list[str]]]] | None = None
        self._bm25_lock = threading.RLock()

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
        metadata: list[dict] | None = None,
    ):
        if len(chunks) != len(vectors):
            raise ValueError(
                f"Chunk/vector count mismatch for {article_id}: "
                f"{len(chunks)} chunks vs {len(vectors)} vectors"
            )
        if metadata is not None and len(metadata) != len(chunks):
            raise ValueError(
                f"Chunk/metadata count mismatch for {article_id}: "
                f"{len(chunks)} chunks vs {len(metadata)} metadata records"
            )

        points = []
        for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
            # Deterministic ID: same article + chunk index -> same point
            point_id = str(
                uuid.uuid5(uuid.NAMESPACE_URL, f"{article_id}_chunk_{index}")
            )
            payload = {
                "article_id": article_id,
                "title": title,
                "category": category,
                "workflow_state": workflow_state,
                "chunk_index": index,
                "text": chunk,
            }
            if metadata is not None:
                payload.update(metadata[index])

            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            )

        if points:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )
            self._invalidate_bm25_cache()

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
        self._invalidate_bm25_cache()
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

    def search_bm25(
        self,
        query: str,
        workflow_states: tuple[str, ...],
        limit: int,
    ) -> list[tuple[object, float]]:
        """Rank stored chunk text with BM25, returning points and lexical scores."""
        query_terms = BM25_TOKEN_RE.findall(query.casefold())
        if not query_terms or limit < 1:
            return []

        documents = [
            (point, terms)
            for point, terms in self._get_bm25_documents()
            if (point.payload or {}).get("workflow_state") in workflow_states
        ]
        if not documents:
            return []

        document_count = len(documents)
        average_length = sum(len(terms) for _, terms in documents) / document_count
        document_frequencies: Counter[str] = Counter()
        for _, terms in documents:
            document_frequencies.update(set(terms))

        query_frequencies = Counter(query_terms)
        k1 = 1.5
        b = 0.75
        scored = []
        for point, terms in documents:
            frequencies = Counter(terms)
            document_length = len(terms)
            score = 0.0
            for term, query_frequency in query_frequencies.items():
                term_frequency = frequencies[term]
                if not term_frequency:
                    continue
                inverse_document_frequency = math.log(
                    1
                    + (document_count - document_frequencies[term] + 0.5)
                    / (document_frequencies[term] + 0.5)
                )
                denominator = term_frequency + k1 * (
                    1 - b + b * document_length / average_length
                )
                score += (
                    inverse_document_frequency
                    * term_frequency
                    * (k1 + 1)
                    / denominator
                    * query_frequency
                )
            if score > 0:
                scored.append((point, score))

        return sorted(scored, key=lambda item: item[1], reverse=True)[:limit]

    def _get_bm25_documents(self) -> list[tuple[object, list[str]]]:
        with self._bm25_lock:
            now = time.monotonic()
            if self._bm25_cache and now - self._bm25_cache[0] < BM25_CACHE_TTL_SECONDS:
                return self._bm25_cache[1]

            points = []
            offset = None
            while True:
                page, offset = self.client.scroll(
                    collection_name=self.collection_name,
                    limit=256,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                points.extend(page)
                if offset is None:
                    break

            documents = [
                (
                    point,
                    BM25_TOKEN_RE.findall(
                        str((point.payload or {}).get("text", "")).casefold()
                    ),
                )
                for point in points
            ]
            self._bm25_cache = (
                now,
                [(point, terms) for point, terms in documents if terms],
            )
            return self._bm25_cache[1]

    def _invalidate_bm25_cache(self) -> None:
        with self._bm25_lock:
            self._bm25_cache = None

    def count_points(self) -> int:
        """Used by the startup check to decide whether a reindex is needed."""
        return self.client.count(
            collection_name=self.collection_name, exact=True
        ).count