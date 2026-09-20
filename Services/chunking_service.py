class ChunkingService:

    def __init__(self, chunk_size: int = 50, chunk_overlap: int = 1):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(self, text: str) -> list[str]:
        if not text:
            return []

        units = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        chunks = []
        current_chunk = []
        current_size = 0

        for unit in units:
            unit_words = unit.split()
            unit_size = len(unit_words)

            if current_chunk and current_size + unit_size > self.chunk_size:
                chunks.append(" ".join(current_chunk))

                # Keep the last logical unit(s) as overlap
                current_chunk = current_chunk[-self.chunk_overlap:]
                current_size = sum(
                    len(item.split()) for item in current_chunk
                )

            current_chunk.append(unit)
            current_size += unit_size

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks