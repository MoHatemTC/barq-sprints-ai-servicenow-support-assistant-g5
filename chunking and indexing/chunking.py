from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


PAGE_RE = re.compile(r"^\s*<!--\s*page:\s*(\d+)\s*-->\s*$")
MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
PLAIN_HEADING_PATTERNS = (
	(re.compile(r"^(Part\s+\d+\s*[·:-]|Appendix\s+[A-Z]\s*[·:-]).*$", re.I), 1),
	(re.compile(r"^(Glossary|Conventions used here|The troubleshooting table).*$", re.I), 2),
)
SECTION_ID_RE = re.compile(r"\b(?:KB|UC)-\d+\b", re.I)
DIAGRAM_RE = re.compile(r"^>\s*\[Diagram\s+p\.(\d+)\]", re.I)
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
SENTENCE_RE = re.compile(r"(?<=[.!?؟])\s+(?=[A-Z0-9`\"'\[(])")


@dataclass
class Block:
	text: str
	page_start: int | None
	page_end: int | None
	heading_path: list[str] = field(default_factory=list)
	content_type: str = "prose"

	@property
	def word_count(self) -> int:
		return len(self.text.split())


def _heading_level(line: str) -> tuple[int, str] | None:
	match = MARKDOWN_HEADING_RE.match(line)
	if match:
		return len(match.group(1)), match.group(2).strip()

	for pattern, level in PLAIN_HEADING_PATTERNS:
		if pattern.match(line.strip()):
			return level, line.strip()

	plain_line = line.strip()
	if (
		len(plain_line) <= 100
		and len(plain_line.split()) <= 12
		and SECTION_ID_RE.search(plain_line)
		and not plain_line.endswith((".", ":", ";"))
	):
		return 2, plain_line
	return None


def _is_table_start(lines: list[str], index: int) -> bool:
	return (
		index + 1 < len(lines)
		and lines[index].lstrip().startswith("|")
		and bool(TABLE_SEPARATOR_RE.match(lines[index + 1]))
	)


def _is_table_line(line: str) -> bool:
	return line.lstrip().startswith("|")


def _content_type(text: str) -> str:
	if text.startswith("> [Diagram p."):
		return "diagram"
	if "\n|" in text or text.lstrip().startswith("|"):
		return "table"
	if "```" in text or "~~~" in text:
		return "code"
	if re.search(r"(?m)^\s*(?:\d+[.)]|[-*])\s+", text):
		return "procedure"
	return "prose"


def parse_blocks(document: str) -> list[Block]:
	lines = document.replace("\r\n", "\n").splitlines()
	blocks: list[Block] = []
	current_page: int | None = None
	heading_stack: list[tuple[int, str]] = []
	index = 0

	def context() -> list[str]:
		return [heading for _, heading in heading_stack]

	def add_block(raw_lines: list[str], page_start: int | None, page_end: int | None) -> None:
		text = "\n".join(raw_lines).strip()
		if text:
			blocks.append(
				Block(
					text=text,
					page_start=page_start,
					page_end=page_end,
					heading_path=context(),
					content_type=_content_type(text),
				)
			)

	while index < len(lines):
		line = lines[index]
		page_match = PAGE_RE.match(line)
		if page_match:
			current_page = int(page_match.group(1))
			index += 1
			continue

		if not line.strip():
			index += 1
			continue

		heading = _heading_level(line)
		if heading:
			level, title = heading
			while heading_stack and heading_stack[-1][0] >= level:
				heading_stack.pop()
			heading_stack.append((level, title))
			add_block([line.strip()], current_page, current_page)
			index += 1
			continue

		if _is_table_start(lines, index):
			table_lines = [line]
			index += 1
			while index < len(lines) and _is_table_line(lines[index]):
				table_lines.append(lines[index])
				index += 1
			add_block(table_lines, current_page, current_page)
			continue

		if FENCE_RE.match(line):
			fence = FENCE_RE.match(line).group(1)[0:3]
			code_lines = [line]
			index += 1
			while index < len(lines):
				code_lines.append(lines[index])
				if lines[index].lstrip().startswith(fence):
					index += 1
					break
				index += 1
			add_block(code_lines, current_page, current_page)
			continue

		if DIAGRAM_RE.match(line):
			diagram_page = int(DIAGRAM_RE.match(line).group(1))
			diagram_lines = [line]
			index += 1
			while index < len(lines):
				if PAGE_RE.match(lines[index]):
					break
				diagram_lines.append(lines[index])
				index += 1
			blocks.append(
				Block(
					text="\n".join(diagram_lines).strip(),
					page_start=diagram_page,
					page_end=current_page or diagram_page,
					heading_path=context(),
					content_type="diagram",
				)
			)
			continue

		prose_lines = [line]
		index += 1
		while index < len(lines):
			next_line = lines[index]
			if (
				not next_line.strip()
				or PAGE_RE.match(next_line)
				or _heading_level(next_line)
				or _is_table_start(lines, index)
				or FENCE_RE.match(next_line)
				or DIAGRAM_RE.match(next_line)
			):
				break
			prose_lines.append(next_line)
			index += 1
		add_block(prose_lines, current_page, current_page)

	return blocks


def _split_sentences(text: str) -> list[str]:
	return [part.strip() for part in SENTENCE_RE.split(text) if part.strip()]


def _split_prose(block: Block, target_words: int, overlap_words: int) -> list[Block]:
	sentences = _split_sentences(block.text)
	if not sentences:
		return [block]

	result: list[Block] = []
	current: list[str] = []
	count = 0
	for sentence in sentences:
		sentence_words = len(sentence.split())
		if current and count + sentence_words > target_words:
			result.append(Block(" ".join(current), block.page_start, block.page_end, block.heading_path, "prose"))
			overlap: list[str] = []
			overlap_count = 0
			for previous in reversed(current):
				previous_count = len(previous.split())
				if overlap_count + previous_count > overlap_words:
					break
				overlap.insert(0, previous)
				overlap_count += previous_count
			current = overlap
			count = overlap_count
		current.append(sentence)
		count += sentence_words
	if current:
		result.append(Block(" ".join(current), block.page_start, block.page_end, block.heading_path, "prose"))
	return result


def _split_protected(block: Block, target_words: int) -> list[Block]:
	if block.word_count <= target_words:
		return [block]

	if block.content_type == "table":
		lines = block.text.splitlines()
		if len(lines) < 3:
			return [block]
		header = lines[:2]
		pieces: list[Block] = []
		rows: list[str] = []
		for line in lines[2:]:
			candidate = "\n".join(header + rows + [line])
			if rows and len(candidate.split()) > target_words:
				pieces.append(Block("\n".join(header + rows), block.page_start, block.page_end, block.heading_path, "table"))
				rows = []
			rows.append(line)
		if rows:
			pieces.append(Block("\n".join(header + rows), block.page_start, block.page_end, block.heading_path, "table"))
		return pieces or [block]

	if block.content_type == "diagram":
		lines = block.text.splitlines()
		label = lines[0]
		if len(lines) >= 3 and lines[1].lstrip().startswith("|") and TABLE_SEPARATOR_RE.match(lines[2]):
			header = [label, lines[1], lines[2]]
			pieces: list[Block] = []
			rows: list[str] = []
			for line in lines[3:]:
				candidate = "\n".join(header + rows + [line])
				if rows and len(candidate.split()) > target_words:
					pieces.append(Block("\n".join(header + rows), block.page_start, block.page_end, block.heading_path, "diagram"))
					rows = []
				rows.append(line)
			if rows:
				pieces.append(Block("\n".join(header + rows), block.page_start, block.page_end, block.heading_path, "diagram"))
			return pieces or [block]
		sections = re.split(
			r"(?m)^\s*>?\s*(?:---+|#{2,6}\s+)",
			"\n".join(lines[1:]),
		)
		sections = [section.strip() for section in sections if section.strip()]
		if len(sections) <= 1:
			return [block]
		pieces = []
		current = [label]
		for section in sections:
			candidate = "\n\n".join(current + [section])
			if len(current) > 1 and len(candidate.split()) > target_words:
				pieces.append(Block("\n\n".join(current), block.page_start, block.page_end, block.heading_path, "diagram"))
				current = [label]
			current.append(section)
		if len(current) > 1:
			pieces.append(Block("\n\n".join(current), block.page_start, block.page_end, block.heading_path, "diagram"))
		return pieces or [block]

	return [block]


def _chunk_blocks(blocks: list[Block], target_words: int, overlap_words: int) -> list[dict]:
	chunks: list[dict] = []
	pending: list[Block] = []
	pending_words = 0

	def emit() -> None:
		nonlocal pending, pending_words
		if not pending:
			return
		text = "\n\n".join(block.text for block in pending)
		pages = [block.page_start for block in pending if block.page_start is not None]
		pages.extend(block.page_end for block in pending if block.page_end is not None)
		headings = pending[-1].heading_path
		chunks.append(
			{
				"chunk_id": f"chunk-{len(chunks):04d}",
				"text": text,
				"metadata": {
					"page_start": min(pages) if pages else None,
					"page_end": max(pages) if pages else None,
					"heading_path": headings,
					"section_ids": sorted(set(SECTION_ID_RE.findall(text.upper()))),
					"content_types": sorted(set(block.content_type for block in pending)),
					"word_count": len(text.split()),
				},
			}
		)
		pending = []
		pending_words = 0

	for block in blocks:
		if block.content_type == "prose":
			pieces = _split_prose(block, target_words, overlap_words)
		elif block.content_type in {"table", "diagram"}:
			pieces = _split_protected(block, target_words)
		else:
			pieces = [block]
		for piece in pieces:
			piece_words = piece.word_count
			protected = piece.content_type in {"table", "diagram", "code", "procedure"}
			if pending and protected:
				emit()
			elif pending and pending_words + piece_words > target_words:
				emit()
			pending.append(piece)
			pending_words += piece_words
	emit()
	return chunks


def build_chunks(input_path: Path, target_words: int = 400, overlap_words: int = 60) -> list[dict]:
	if target_words < 1 or overlap_words < 0:
		raise ValueError("target_words must be positive and overlap_words cannot be negative")
	document = input_path.read_text(encoding="utf-8")
	blocks = parse_blocks(document)
	chunks = _chunk_blocks(blocks, target_words, overlap_words)
	document_id = input_path.parent.name
	source_file = input_path.name
	for chunk in chunks:
		chunk["metadata"]["document_id"] = document_id
		chunk["metadata"]["source_file"] = source_file
	return chunks


def main() -> None:
	parser = argparse.ArgumentParser(description="Create metadata-rich chunks from parsed Markdown.")
	parser.add_argument(
		"--input",
		type=Path,
		default=Path("data/parsed/doc_001/document.md"),
		help="Path to document.md",
	)
	parser.add_argument(
		"--output",
		type=Path,
		default=Path("data/parsed/doc_001/chunks.json"),
		help="Path for the JSON chunk output",
	)
	parser.add_argument("--target-words", type=int, default=400)
	parser.add_argument("--overlap-words", type=int, default=60)
	args = parser.parse_args()

	chunks = build_chunks(args.input, args.target_words, args.overlap_words)
	args.output.parent.mkdir(parents=True, exist_ok=True)
	args.output.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
	print(f"Wrote {len(chunks)} chunks to {args.output}")


if __name__ == "__main__":
	main()
