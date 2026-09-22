import re


class ChunkingService:

    def __init__(self, chunk_size: int = 70, chunk_overlap: int = 1):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(self, text: str) -> list[str]:
        if not text:
            return []

        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?؟])\s+|\n+", text.strip())
            if sentence.strip()
        ]
        if self.chunk_overlap > 1:
            raise ValueError("chunk_overlap supports at most one sentence")

        chunks = []
        current_sentences = []
        current_size = 0

        for sentence in sentences:
            sentence_size = len(sentence.split())
            if (
                current_sentences
                and current_size + sentence_size > self.chunk_size
            ):
                chunks.append(" ".join(current_sentences))
                current_sentences = (
                    current_sentences[-self.chunk_overlap:]
                    if self.chunk_overlap
                    else []
                )
                current_size = sum(
                    len(item.split()) for item in current_sentences
                )

            current_sentences.append(sentence)
            current_size += sentence_size

        if current_sentences:
            chunks.append(" ".join(current_sentences))

        words = text.split()
        target_chunks = 3 if len(words) <= 70 else 4
        if len(chunks) != target_chunks:
            chunk_size = max(1, len(words) // target_chunks)
            chunks = [
                " ".join(
                    words[index * chunk_size:
                          (index + 1) * chunk_size]
                )
                for index in range(target_chunks - 1)
            ]
            chunks.append(" ".join(words[(target_chunks - 1) * chunk_size:]))
            chunks = [chunk for chunk in chunks if chunk]

            while len(chunks) < target_chunks:
                chunks.append(chunks[-1] if chunks else text.strip())

        return chunks