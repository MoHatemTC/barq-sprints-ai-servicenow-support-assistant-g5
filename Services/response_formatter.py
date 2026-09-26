from dataclasses import dataclass, field
import re


@dataclass
class Step:
    number: int
    text: str
    sources: list[str]


@dataclass
class FormattedResponse:
    human_review_required: bool
    escalation_message: str | None = None
    steps: list[Step] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    rejected_steps: list[dict] = field(default_factory=list)

    def render(self) -> str:
        if self.human_review_required:
            return self.escalation_message or ""
        lines = ["Suggested resolution (pending human approval):"]
        lines += [f"{s.number}. {s.text}" for s in self.steps]
        lines += ["", "Sources:"]
        lines += [f"- {s['article_id']}: {s['title']}" for s in self.sources]
        return "\n".join(lines)


def build_escalation(reason: str, incident_number: str | None = None) -> FormattedResponse:
    ref = f" for incident {incident_number}" if incident_number else ""
    message = (
        f"HUMAN REVIEW REQUIRED{ref}: {reason} "
        "No resolution procedure was generated. "
        "Please escalate this incident to a service desk agent."
    )
    return FormattedResponse(human_review_required=True, escalation_message=message)


def format_response(agent_output, chunks, human_review_required=None, incident_number=None):
    chunk_list = list(chunks or [])

    if human_review_required is None:
        human_review_required = not chunk_list  # no chunks -> escalate

    if human_review_required or not chunk_list:
        return build_escalation(
            "No approved knowledge base article matched with enough confidence.",
            incident_number,
        )

    text = extract_text(agent_output).strip()
    if not text or text.upper().startswith("NO_ANSWER"):
        return build_escalation(
            "The knowledge base does not contain a supported answer.",
            incident_number,
        )

    steps, rejected, titles = validate_steps(split_steps(text), chunk_list)

    if not steps:
        response = build_escalation(
            "The agent output could not be grounded in retrieved articles.",
            incident_number,
        )
        response.rejected_steps = rejected
        return response

    used = list(dict.fromkeys(s for step in steps for s in step.sources))
    return FormattedResponse(
        human_review_required=False,
        steps=steps,
        sources=[{"article_id": a, "title": titles[a]} for a in used],
        rejected_steps=rejected,
    )

STEP_PREFIX_RE = re.compile(r"^\s*(?:\d+\s*[\.\)]|[-*\u2022])\s*")
LIST_LINE_RE = re.compile(r"^\s*(?:\d+\s*[\.\)]|[-*\u2022])\s+\S")


def split_steps(agent_output: str) -> list[str]:
    lines = [ln.strip() for ln in agent_output.splitlines() if ln.strip()]
    listed = [ln for ln in lines if LIST_LINE_RE.match(ln)]
    candidates = listed or lines
    return [STEP_PREFIX_RE.sub("", ln).strip() for ln in candidates]


CITATION_RE = re.compile(r"\[(?:Article:\s*)?([A-Za-z]{2,}\d+)\]")

def validate_steps(step_texts, chunks):
    titles = {}
    for c in chunks:
        titles.setdefault(str(c.get("article_id")), str(c.get("title") or ""))

    steps, rejected = [], []
    for text in step_texts:
        cited = list(dict.fromkeys(CITATION_RE.findall(text)))
        if not cited:
            rejected.append({"text": text, "reason": "no citation"})
            continue
        unknown = [c for c in cited if c not in titles]
        if unknown:
            rejected.append({"text": text, "reason": f"unknown source: {', '.join(unknown)}"})
            continue
        steps.append(Step(number=len(steps) + 1, text=text, sources=cited))
    return steps, rejected, titles

def compute_confidence(chunks) -> float:
    """AI Confidence (FR-17): highest retrieval score among the chunks, 0.0 if none."""
    scores = [
        float(c["score"])
        for c in (chunks or [])
        if isinstance(c.get("score"), (int, float))
    ]
    return round(max(scores), 4) if scores else 0.0

def extract_text(content) -> str:
    """Gemini may return a str or a list of blocks; keep only the text."""
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)

def to_writeback_payload(response, confidence: float) -> dict:
    """Payload for the ServiceNow write-back (FR-16)."""
    escalated = response.human_review_required
    return {
        "ai_suggested_response": response.render(),
        "ai_confidence": confidence,
        "human_review_required": True,  # FR-16: every processed incident is reviewed by a human
        "escalated": escalated,         # True = no fix drafted, hand-off note only
        "citations": [] if escalated else [s["article_id"] for s in response.sources],
    }