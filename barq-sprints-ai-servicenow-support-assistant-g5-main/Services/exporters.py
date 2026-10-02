"""Task 6 exporters: Markdown, HTML (stdlib only) and JSON write-back payload."""

import html
import json
import re


def to_markdown(response) -> str:
    if response.human_review_required:
        return f"## Human Review Required\n\n{response.escalation_message}\n"
    lines = ["## Suggested resolution (pending human approval)", ""]
    lines += [f"{s.number}. {s.text}" for s in response.steps]
    lines += ["", "**Sources**", ""]
    lines += [f"- {a['article_id']}: {a['title']}" for a in response.sources]
    return "\n".join(lines) + "\n"


def _inline(text: str) -> str:
    # Escape FIRST so incident/LLM text can never inject HTML, then apply **bold**.
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(text))


def markdown_to_html(md: str) -> str:
    """Tiny converter for the subset we emit: headings, numbered/bullet lists, bold."""
    out, mode = [], None

    def close():
        nonlocal mode
        if mode:
            out.append(f"</{mode}>")
            mode = None

    for raw in md.splitlines():
        line = raw.strip()
        if not line:
            close()
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        ordered = re.match(r"^\d+\.\s+(.*)$", line)
        bullet = re.match(r"^-\s+(.*)$", line)
        if heading:
            close()
            n = len(heading.group(1))
            out.append(f"<h{n}>{_inline(heading.group(2))}</h{n}>")
        elif ordered or bullet:
            wanted = "ol" if ordered else "ul"
            if mode != wanted:
                close()
                out.append(f"<{wanted}>")
                mode = wanted
            out.append(f"<li>{_inline((ordered or bullet).group(1))}</li>")
        else:
            close()
            out.append(f"<p>{_inline(line)}</p>")
    close()
    return "\n".join(out)


def to_html(response) -> str:
    return markdown_to_html(to_markdown(response))


def to_json(response, confidence: float) -> str:
    from Services.response_formatter import to_writeback_payload
    return json.dumps(to_writeback_payload(response, confidence), indent=2)