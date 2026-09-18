from Services.text_cleaner import clean_html_text
from Services.embedding_service import EmbeddingService
from Services.chunking_service import ChunkingService


html_text = """
<h1>Application Won't Launch or Install</h1>
<p>Confirm the software is compatible with the current OS and hardware.</p>
<p>Verify the installer comes from a trusted source and matches the system's architecture (32-bit vs 64-bit).</p>
<p>Check that the account has the admin rights the installer needs.</p>
<p>Free up disk space if the drive is near capacity.</p>
<p>Remove leftover files from a previous install attempt before retrying.</p>
<p>Reinstall the application to repair corrupted files or missing components.</p>
"""

clean_text = clean_html_text(html_text)

chunker = ChunkingService(
    chunk_size=30,
    chunk_overlap=5
)

chunks = chunker.chunk_text(clean_text)

embedding_service = EmbeddingService()

vectors = embedding_service.embed_chunks(chunks)

print("Number of chunks:", len(chunks))
print("Number of vectors:", len(vectors))

for i, vector in enumerate(vectors):
    print(f"Chunk {i}:")
    print("  Words:", len(chunks[i].split()))
    print("  Vector dimension:", len(vector))
    print("  First 5 values:", vector[:5])