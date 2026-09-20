"""Task 5: filtered KB retrieval and a read-only LangChain agent."""

import os
from typing import Any

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny

try:
    from sentence_transformers import SentenceTransformer
    print("SentenceTransformers is available for embedding generation.")
except ImportError:  # pragma: no cover
    print("SentenceTransformers is not installed.")
    SentenceTransformer = None

from langchain_core.tools import tool

load_dotenv()

QDRANT_URL = os.getenv(
    "QDRANT_URL",
    "https://trio-levitate-unicorn.ngrok-free.dev:443",
)
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "kb_articles")
EMBEDDING_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL_NAME",
    "all-MiniLM-L6-v2",
)
MIN_SIMILARITY_SCORE = float(
    os.getenv("SCORE_THRESHOLD") or "0.60"
)
ALLOWED_WORKFLOW_STATES = frozenset({"published", "approved"})


class KnowledgeRetriever:
    """Generate embeddings and return approved, high-confidence KB chunks."""

    def __init__(
        self,
        client: QdrantClient,
        embedding_model: Any,
        collection_name: str = COLLECTION_NAME,
        minimum_score: float = MIN_SIMILARITY_SCORE,
        allowed_workflow_states: frozenset[str] = ALLOWED_WORKFLOW_STATES,
    ) -> None:
        self.client = client
        self.embedding_model = embedding_model
        self.collection_name = collection_name
        self.minimum_score = minimum_score
        self.allowed_workflow_states = allowed_workflow_states

    def _calculate_embedding(self, query: str) -> list[float]:
        if not query or not query.strip():
            raise ValueError("Query text cannot be empty.")

        vector = self.embedding_model.encode(
            query.strip(),
            normalize_embeddings=True,
            convert_to_numpy=False,
        )
        print(f"Generated embedding vector of length {len(vector)}.")
        return [float(value) for value in vector]

    def search(self, query: str) -> list[dict[str, Any]]:
        """Search Qdrant and return only approved chunks above the threshold."""
        query_vector = self._calculate_embedding(query)
        workflow_filter = Filter(
            must=[
                FieldCondition(
                    key="workflow_state",
                    match=MatchAny(any=list(self.allowed_workflow_states)),
                )
            ]
        )
        search_response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=workflow_filter,
            limit=5,
            with_payload=True,
            score_threshold=self.minimum_score,
        )
        search_results = search_response.points
        print(f"Search returned {len(search_results)} results.")
        print(f"Search results: {search_results}")

        valid_hits: list[dict[str, Any]] = []
        for hit in search_results:
            payload = getattr(hit, "payload", None) or {}
            if not isinstance(payload, dict):
                continue

            workflow_state = str(payload.get("workflow_state", "")).strip().lower()
            score = float(getattr(hit, "score", 0.0) or 0.0)
            if workflow_state not in self.allowed_workflow_states:
                continue
            if score < self.minimum_score:
                continue

            valid_hits.append(
                {
                    "article_id": payload.get("article_id"),
                    "title": payload.get("title"),
                    "content": payload.get("text") or payload.get("content") or "",
                    "score": round(score, 4),
                    "workflow_state": workflow_state,
                }
            )

        print(f"Returning {len(valid_hits)} approved KB chunks.")
        return valid_hits


_retriever: KnowledgeRetriever | None = None


def get_knowledge_retriever() -> KnowledgeRetriever:
    """Create the Qdrant client and embedding model on first use."""
    global _retriever
    if _retriever is not None:
        return _retriever

    if SentenceTransformer is None:
        raise ImportError(
            "Install sentence-transformers to enable KB retrieval."
        )

    print("Connecting to Qdrant database...")
    client = QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
        headers={"ngrok-skip-browser-warning": "true"},
    )
    print(f"Connected to collection '{COLLECTION_NAME}'.")
    print("Loading embedding model...")
    embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    print(f"Embedding model '{EMBEDDING_MODEL_NAME}' loaded.")
    _retriever = KnowledgeRetriever(client, embedding_model)
    return _retriever


def count_kb_articles() -> tuple[int | None, int]:
    """Return the stored vector-point count and unique KB article count."""
    client = get_knowledge_retriever().client
    collection_info = client.get_collection(collection_name=COLLECTION_NAME)
    article_ids: set[str] = set()
    offset = None

    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            offset=offset,
            limit=100,
            with_payload=["article_id"],
            with_vectors=False,
        )
        for point in points:
            article_id = (point.payload or {}).get("article_id")
            if article_id:
                article_ids.add(str(article_id))

        if offset is None:
            break

    return collection_info.points_count, len(article_ids)


@tool
def retrieve_knowledge(query: str) -> list[dict[str, Any]]:
    """Read-only search tool for approved ServiceNow KB chunks."""
    if not query or not query.strip():
        return []

    try:
        print(f"Calculating embedding for query: {query}")
        print(f"Searching collection '{COLLECTION_NAME}'...")
        return get_knowledge_retriever().search(query)
    except Exception as exc:  # pragma: no cover
        print(f"KB retrieval error: {exc}")
        return []


def create_read_only_agent():
    """Build an agent with exactly one read-only KB retrieval tool."""
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model=os.getenv("LLM_MODEL", "gemini-2.5-flash"),
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0,
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Use retrieve_knowledge to answer using only approved KB chunks. "
                "This agent is read-only and has no write, update, or delete tools. "
                "If no approved chunks are returned, request human review.",
            ),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )
    agent = create_tool_calling_agent(llm, [retrieve_knowledge], prompt)
    return AgentExecutor(agent=agent, tools=[retrieve_knowledge], verbose=True)


if __name__ == "__main__":
    try:
        chunk_count, article_count = count_kb_articles()
        print(f"Vector chunks in Qdrant: {chunk_count}")
        print(f"Unique KB articles in Qdrant: {article_count}")
    except Exception as exc:
        print(f"KB article count error: {exc}")

    test_query = "wifi keeps disconnecting on my laptop"
    print(retrieve_knowledge.invoke({"query": test_query}))