from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from Services.embedding_service import EmbeddingService
from Services.qdrant_service import QdrantService

load_dotenv()


def load_chunks(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Chunk JSON must contain a list")

    for index, chunk in enumerate(data):
        if not isinstance(chunk, dict) or not isinstance(chunk.get("text"), str):
            raise ValueError(f"Invalid chunk at index {index}: expected an object with text")
        if not isinstance(chunk.get("metadata"), dict):
            raise ValueError(f"Invalid chunk at index {index}: metadata must be an object")
    return data


def index_chunks(
    input_path: Path,
    article_id: str,
    title: str,
    category: str,
    workflow_state: str,
) -> dict[str, int | str]:
    chunks = load_chunks(input_path)
    embedder = EmbeddingService()
    qdrant = QdrantService()

    texts = [chunk["text"] for chunk in chunks]
    vectors = embedder.embed_chunks([f"{title}\n\n{text}" for text in texts])
    metadata = [chunk["metadata"] | {"chunk_id": chunk.get("chunk_id")} for chunk in chunks]

    qdrant.delete_article(article_id)
    qdrant.upsert_chunks(
        article_id=article_id,
        title=title,
        category=category,
        workflow_state=workflow_state,
        chunks=texts,
        vectors=vectors,
        metadata=metadata,
    )
    return {"article_id": article_id, "chunks": len(texts), "vectors": len(vectors)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Embed and index structure-aware Markdown chunks in Qdrant.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/parsed/doc_001/chunks.json"),
        help="Path to generated chunks.json",
    )
    parser.add_argument("--article-id", default="doc_001")
    parser.add_argument(
        "--title",
        default="AI ServiceNow IT Incident Resolution Assistant Knowledge Base",
    )
    parser.add_argument("--category", default="technical_runbook")
    parser.add_argument("--workflow-state", default="published")
    args = parser.parse_args()

    result = index_chunks(
        input_path=args.input,
        article_id=args.article_id,
        title=args.title,
        category=args.category,
        workflow_state=args.workflow_state,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
