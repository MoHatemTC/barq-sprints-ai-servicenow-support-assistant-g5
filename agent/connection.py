import os
from qdrant_client import QdrantClient

# ---------------------------------------------------------
# 1. Configuration
# Replace these with your actual host URL and credentials
# ---------------------------------------------------------
QDRANT_URL = os.getenv("QDRANT_URL", "https://your-cluster-url.qdrant.tech:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "your-api-key-here")
COLLECTION_NAME = "servicenow_articles"  # Name of your teammate's collection

# ---------------------------------------------------------
# 2. Initialize Client
# ---------------------------------------------------------
# If using an unsecured self-hosted instance without an API key,
# you can omit the api_key parameter.
client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
    # timeout=10.0, # Optional: adjust timeout if needed
)

# ---------------------------------------------------------
# 3. Test Connection & Inspect Collections
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