#search steps:
#input: sanitized_query, truncated_description, and is_safe in a json
# Connect with the database (qdrant)
# calculate query embeddings
# semantic search ( Returns matched chunks with similarity scores.)
#if the retrived chunk reached a threshold 70% pass it else reject it 
# the meta data need to ckeck if it was draft it needs to refuse it else it will pass it 
#requirements:
#use langchain
#use a tool to do the search steps


#Implementation:
# Connect with the database
print("Starting...")
import os
from typing import Any

from qdrant_client import QdrantClient

try:
    from sentence_transformers import SentenceTransformer
    print("SentenceTransformers is available for embedding generation.")
except ImportError:  # pragma: no cover
    print("SentenceTransformers is not installed. Install it with: pip install sentence-transformers")
    SentenceTransformer = None

try:
    from langchain_core.tools import tool
    print("LangChain tools are available for creating retrieval tools.")
except ImportError:  # pragma: no cover
    try:
        from langchain.tools import tool
        print("LangChain tools are available for creating retrieval tools.")
    except ImportError:  # pragma: no cover
        print("LangChain is not installed. Install it with: pip install langchain")
        def tool(*args, **kwargs):
            def decorator(func):
                return func
            return decorator

# ---------------------------------------------------------
# 1. Configuration
# Replace these with your actual host URL and credentials
# ---------------------------------------------------------
QDRANT_URL = os.getenv("QDRANT_URL", "https://trio-levitate-unicorn.ngrok-free.dev:443")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "your-api-key-here")
COLLECTION_NAME = "kb_articles"
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
MIN_SIMILARITY_SCORE = 0.70
ALLOWED_WORKFLOW_STATES = {"published", "approved"}



from qdrant_client import QdrantClient
print("Connecting to Qdrant database...")





# ---------------------------------------------------------
# 2. Initialize Client
# ---------------------------------------------------------
client = QdrantClient(
    url="https://trio-levitate-unicorn.ngrok-free.dev",
    headers={"ngrok-skip-browser-warning": "true"}
)
collections = client.get_collections()
print(collections)








# ---------------------------------------------------------
# 3. Query Embedding Section
# ---------------------------------------------------------
if SentenceTransformer is not None:
    embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
else:
    embedding_model = None


def calculate_query_embedding(query: str) -> list[float]:
    """
    Convert a cleaned user query into a dense vector embedding.
    """
    if not query or not str(query).strip():
        raise ValueError("Query text cannot be empty for embedding generation.")

    if embedding_model is None:
        raise ImportError(
            "SentenceTransformers is not installed. Install it with: pip install sentence-transformers"
        )

    vector = embedding_model.encode(
        str(query).strip(),
        normalize_embeddings=True,
        convert_to_numpy=False,
    )
    return [float(value) for value in vector]


@tool
def retrieve_knowledge(query: str) -> list[dict[str, Any]]:
    """
    Read-only retrieval tool for approved ServiceNow KB articles.
    Returns relevant chunks with similarity scores and filters out draft content.
    """
    if not query or not str(query).strip():
        return []

    try:
        print(f"Calculating embedding for query: {query}")
        query_vector = calculate_query_embedding(str(query).strip())
    except Exception as exc:  # pragma: no cover
        print(f"Embedding error: {exc}")
        return []

    try:
        print(f"Performing semantic search in collection '{COLLECTION_NAME}'...")
        search_results = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=5,
            with_payload=True,
        )
        print(f"Search returned {len(search_results)} results.")


        """
        points = client.scroll(
        collection_name="kb_articles",
        limit=5,
        with_payload=True,
        with_vectors=False,
        )
        print(points)

        """



    except Exception as exc:  # pragma: no cover
        print(f"Qdrant search error: {exc}")
        return []
    
    valid_hits: list[dict[str, Any]] = []
    for hit in search_results:
        payload = getattr(hit, "payload", None) or {}
        if not isinstance(payload, dict):
            continue

        workflow_state = str(payload.get("workflow_state", "")).strip().lower()
        if workflow_state not in ALLOWED_WORKFLOW_STATES:
            continue

        score = float(getattr(hit, "score", 0.0) or 0.0)
        if score < MIN_SIMILARITY_SCORE:
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

    return valid_hits


def create_read_only_agent():
    """
    Build a LangChain agent with a single read-only retrieval tool.
    """
    try:
        from langchain.agents import AgentExecutor, create_tool_calling_agent
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI
    except ImportError:  # pragma: no cover
        return None

    llm = ChatOpenAI(
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        temperature=0,
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a ServiceNow support assistant. Use the retrieve_knowledge tool to answer using only approved KB articles. Never use write/update/delete tools. If no useful chunks are returned, ask for human review.",
            ),
            ("human", "{input}"),
        ]
    )

    agent = create_tool_calling_agent(llm, [retrieve_knowledge], prompt)
    return AgentExecutor(agent=agent, tools=[retrieve_knowledge], verbose=True)


# Example usage from the rest of the pipeline:
# cleaned_query = sanitized_query or truncated_description
# matches = retrieve_knowledge.invoke({"query": cleaned_query})
# if not matches:
#     human_review_required = True

# ---------------------------------------------------------
# 4. Test Connection & Inspect Collections
# ---------------------------------------------------------
try:
    # Check if the connection works by listing available collections
    collections_response = client.get_collections()
    available_collections = [c.name for c in collections_response.collections]
    print("Connected successfully!")
    print(f"Available collections: {available_collections}")

    if COLLECTION_NAME in available_collections:
        # Get metadata, vector dimensions, and distance metric
        collection_info = client.get_collection(collection_name=COLLECTION_NAME)
        print(f"\nCollection '{COLLECTION_NAME}' details:")
        print(f" - Points count: {collection_info.points_count}")
        print(f" - Vector config: {collection_info.config.params.vectors}")
    else:
        print(f"\nWarning: Collection '{COLLECTION_NAME}' not found.")

except Exception as e:
    print(f"Failed to connect to Qdrant: {e}")

