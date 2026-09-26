import re

SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟])\s+|\n+")


class ChunkingService:

    def __init__(self, chunk_size: int = 70, chunk_overlap: int = 1):
        if chunk_size < 1 or chunk_overlap < 0:
            raise ValueError("Invalid chunking configuration")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(self, text: str) -> list[str]:
        if not text:
            return []

        units = [u.strip() for u in SENTENCE_SPLIT.split(text.strip()) if u.strip()]

        chunks, current, size = [], [], 0
        for unit in units:
            n = len(unit.split())
            if current and size + n > self.chunk_size:
                chunks.append(" ".join(current))
                current = current[-self.chunk_overlap:] if self.chunk_overlap else []
                size = sum(len(u.split()) for u in current)
            current.append(unit)
            size += n

        if current:
            chunks.append(" ".join(current))
        return chunks