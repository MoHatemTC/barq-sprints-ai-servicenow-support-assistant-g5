from Services.embedding_service import EmbeddingService


embedding_service = EmbeddingService()

text = """
Check that the account has the admin rights the installer needs.
"""

vector = embedding_service.embed_text(text)

print("Vector dimension:", len(vector))
print("First 10 values:", vector[:10])