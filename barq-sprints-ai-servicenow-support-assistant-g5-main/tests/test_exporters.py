import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Services.exporters import markdown_to_html, to_html, to_json, to_markdown
from Services.response_formatter import compute_confidence, format_response

CHUNKS = [{"article_id": "KB0000001", "title": "Fix WiFi disconnections", "score": 0.5058}]


def test_markdown_has_numbered_steps_and_sources():
    md = to_markdown(format_response("1. Do X. [Article: KB0000001]", CHUNKS))
    assert "1. Do X. [Article: KB0000001]" in md
    assert "- KB0000001: Fix WiFi disconnections" in md


def test_html_structure():
    h = to_html(format_response("1. Do X. [Article: KB0000001]\n2. Do Y. [Article: KB0000001]", CHUNKS))
    assert "<ol>" in h and h.count("<li>") == 3 and "<ul>" in h and "<strong>Sources</strong>" in h


def test_html_escapes_injected_markup():
    h = markdown_to_html("1. <script>alert(1)</script> [Article: KB0000001]")
    assert "<script>" not in h and "&lt;script&gt;" in h


def test_escalation_exports():
    r = format_response("x", [], incident_number="INC1")
    assert "Human Review Required" in to_markdown(r)
    assert "<h2>Human Review Required</h2>" in to_html(r)
    assert "<ol>" not in to_html(r)


def test_json_export_is_valid_and_reviewed():
    r = format_response("1. Do X. [Article: KB0000001]", CHUNKS)
    data = json.loads(to_json(r, compute_confidence(CHUNKS)))
    assert data["human_review_required"] is True and data["citations"] == ["KB0000001"]