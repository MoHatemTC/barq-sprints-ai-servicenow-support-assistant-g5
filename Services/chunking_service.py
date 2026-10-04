"""Hybrid Chunking Service implementing structural chunking with meaning-based fallback.

Strategy:
1. Structural Chunking: Parses Markdown headers (#, ##, etc.), section boundaries, code blocks, tables, and lists.
2. Meaning/Semantic Fallback: If no structural headers are present, or when a structural block exceeds `chunk_size`,
   splits by sentence/meaning boundaries using regex and groups sentence units into semantic chunks.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟])\s+|\n+")
MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
PLAIN_HEADING_RE = re.compile(r"^(Section\s+\d+|Part\s+\d+|Glossary|Prerequisites|Steps|Troubleshooting|KB-\d+|UC-\d+).*$", re.IGNORECASE | re.MULTILINE)
FENCE_RE = re.compile(r"^\s*(```|~~~)")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")


class HybridChunker:
    """Structural chunking with fallback to meaning-based (sentence) chunking."""

    def __init__(self, chunk_size: int = 70, chunk_overlap: int = 1):
        if chunk_size < 1 or chunk_overlap < 0:
            raise ValueError("Invalid chunking configuration")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def _split_into_sentences(self, text: str) -> List[str]:
        return [u.strip() for u in SENTENCE_SPLIT.split(text.strip()) if u.strip()]

    def _chunk_meaning_units(self, units: List[str], heading_path: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Group sentence/meaning units into coherent chunks respecting chunk_size & overlap."""
        chunks: List[Dict[str, Any]] = []
        current: List[str] = []
        size = 0

        for unit in units:
            n = len(unit.split())
            if current and size + n > self.chunk_size:
                chunk_str = " ".join(current)
                chunks.append({
                    "text": chunk_str,
                    "heading_path": heading_path or [],
                    "content_type": "semantic_prose",
                    "strategy": "meaning"
                })
                current = current[-self.chunk_overlap:] if self.chunk_overlap else []
                size = sum(len(u.split()) for u in current)
            current.append(unit)
            size += n

        if current:
            chunk_str = " ".join(current)
            chunks.append({
                "text": chunk_str,
                "heading_path": heading_path or [],
                "content_type": "semantic_prose",
                "strategy": "meaning"
            })
        return chunks

    def chunk_document(self, text: str) -> List[Dict[str, Any]]:
        """Perform structural chunking with meaning-based fallback."""
        if not text or not text.strip():
            return []

        cleaned_text = text.strip()
        lines = cleaned_text.splitlines()

        # Step 1: Detect structural elements (headings, tables, code fences)
        has_headings = bool(MARKDOWN_HEADING_RE.search(cleaned_text) or PLAIN_HEADING_RE.search(cleaned_text))

        # Fallback to meaning-based chunking if no structural headings exist
        if not has_headings:
            units = self._split_into_sentences(cleaned_text)
            return self._chunk_meaning_units(units, heading_path=[])

        # Structural Chunking Algorithm
        structural_blocks: List[Dict[str, Any]] = []
        current_heading_stack: List[Tuple[int, str]] = []
        current_block_lines: List[str] = []
        in_code_fence = False

        def current_path() -> List[str]:
            return [h[1] for h in current_heading_stack]

        def flush_block(content_type: str = "prose"):
            nonlocal current_block_lines
            if not current_block_lines:
                return
            block_text = "\n".join(current_block_lines).strip()
            if block_text:
                structural_blocks.append({
                    "text": block_text,
                    "heading_path": current_path(),
                    "content_type": content_type,
                    "strategy": "structural"
                })
            current_block_lines = []

        i = 0
        while i < len(lines):
            line = lines[i]

            # Code fence handling
            if FENCE_RE.match(line):
                if in_code_fence:
                    current_block_lines.append(line)
                    flush_block(content_type="code")
                    in_code_fence = False
                else:
                    flush_block(content_type="prose")
                    in_code_fence = True
                    current_block_lines.append(line)
                i += 1
                continue

            if in_code_fence:
                current_block_lines.append(line)
                i += 1
                continue

            # Heading matching
            md_match = MARKDOWN_HEADING_RE.match(line)
            plain_match = PLAIN_HEADING_RE.match(line) if not md_match else None

            if md_match or plain_match:
                flush_block(content_type="prose")
                if md_match:
                    level = len(md_match.group(1))
                    title = md_match.group(2).strip()
                else:
                    level = 2
                    title = line.strip()

                while current_heading_stack and current_heading_stack[-1][0] >= level:
                    current_heading_stack.pop()
                current_heading_stack.append((level, title))

                current_block_lines.append(line)
                i += 1
                continue

            # Table matching
            if TABLE_ROW_RE.match(line):
                if current_block_lines and not any(TABLE_ROW_RE.match(l) for l in current_block_lines):
                    flush_block(content_type="prose")
                current_block_lines.append(line)
                i += 1
                if i < len(lines) and not TABLE_ROW_RE.match(lines[i]):
                    flush_block(content_type="table")
                continue

            if not line.strip():
                if current_block_lines:
                    flush_block(content_type="prose")
                i += 1
                continue

            current_block_lines.append(line)
            i += 1

        flush_block(content_type="prose")

        # Step 2: Combine structural blocks and apply meaning-based sub-chunking if block > chunk_size
        final_chunks: List[Dict[str, Any]] = []

        for block in structural_blocks:
            words = len(block["text"].split())
            if words > self.chunk_size:
                # Sub-chunk large structural blocks using meaning boundaries
                sentences = self._split_into_sentences(block["text"])
                sub_chunks = self._chunk_meaning_units(sentences, heading_path=block["heading_path"])
                for sc in sub_chunks:
                    sc["strategy"] = "hybrid_structural_meaning"
                final_chunks.extend(sub_chunks)
            else:
                final_chunks.append(block)

        return final_chunks

    def chunk_text(self, text: str) -> List[str]:
        """Backward-compatible helper returning plain text list of chunks."""
        chunks = self.chunk_document(text)
        return [c["text"] for c in chunks]


class ChunkingService(HybridChunker):
    """Wrapper class maintaining exact interface compatibility for existing callers."""
    pass