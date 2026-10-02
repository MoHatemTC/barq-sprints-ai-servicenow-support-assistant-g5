import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Services.response_formatter import (
    CITATION_RE,
    compute_confidence,
    extract_text,
    format_response,
    split_steps,
    to_writeback_payload,
)
from utils.console_tracer import print_execution_trace

CHUNKS = [
    {"article_id": "KB0000001", "title": "Fix WiFi disconnections", "score": 0.5058,
     "content": "Forget the WiFi network and reconnect."},
    {"article_id": "KB0000002", "title": "Reset VPN client", "score": 0.31,
     "content": "Reinstall the VPN client."},
]
INCIDENT = {
    "original_number": "INC0010001", "sys_id": "abc123",
    "sanitized_query": "wifi drops", "truncated_description": "wifi drops", "is_safe": True,
}


# ---- Spec case 1: strict citation enforcement ----
def test_numbered_steps_have_inline_citations():
    out = "Here is the fix:\n1. Forget the network. [Article: KB0000001]\n2) Reset the VPN. [KB0000002]"
    r = format_response(out, CHUNKS)
    assert not r.human_review_required
    assert [s.number for s in r.steps] == [1, 2]
    assert all(CITATION_RE.search(s.text) for s in r.steps)
    assert "1. Forget the network. [Article: KB0000001]" in r.render()


def test_uncited_step_is_rejected():
    r = format_response("1. Do X. [Article: KB0000001]\n2. Run rm -rf /", CHUNKS)
    assert len(r.steps) == 1
    assert r.rejected_steps[0]["reason"] == "no citation"


def test_unknown_source_is_rejected():
    r = format_response("1. Do X. [Article: KB0000001]\n2. Do Y. [Article: KB9999999]", CHUNKS)
    assert len(r.steps) == 1
    assert r.rejected_steps[0]["reason"].startswith("unknown source")


def test_gemini_block_list_input():
    blocks = [{"type": "text", "text": "1. Do X. [Article: KB0000001]", "extras": {"signature": "x"}}]
    assert extract_text(blocks) == "1. Do X. [Article: KB0000001]"
    assert format_response(blocks, CHUNKS).steps[0].sources == ["KB0000001"]


def test_split_steps_drops_intro_and_markers():
    assert split_steps("Intro:\n1. A\n2) B\n- C") == ["A", "B", "C"]
    assert split_steps("A\nB") == ["A", "B"]


# ---- Spec case 2: fallback handling ----
def test_forced_human_review_escalates_without_procedure():
    r = format_response("1. Do X. [Article: KB0000001]", CHUNKS,
                        human_review_required=True, incident_number="INC0010001")
    text = r.render()
    assert r.human_review_required and r.steps == []
    assert "HUMAN REVIEW REQUIRED" in text and "INC0010001" in text
    assert "was generated. Please" in text  # catches the missing-space bug
    assert "1." not in text


def test_empty_chunks_escalate():
    assert format_response("1. Do X. [Article: KB0000001]", []).human_review_required


def test_no_answer_escalates():
    assert format_response("NO_ANSWER", CHUNKS).human_review_required


def test_nothing_grounded_escalates_and_keeps_rejections():
    r = format_response("1. Do X\n2. Do Y", CHUNKS)
    assert r.human_review_required and len(r.rejected_steps) == 2


# ---- Confidence and write-back payload ----
def test_confidence_is_max_score_or_zero():
    assert compute_confidence(CHUNKS) == 0.5058
    assert compute_confidence([]) == 0.0
    assert compute_confidence([{"article_id": "KB1"}]) == 0.0


def test_payload_always_requires_human_review():
    ok = to_writeback_payload(format_response("1. Do X. [Article: KB0000001]", CHUNKS), 0.5058)
    esc = to_writeback_payload(format_response("x", []), 0.0)
    assert ok["human_review_required"] is True and ok["escalated"] is False
    assert ok["citations"] == ["KB0000001"]
    assert esc["human_review_required"] is True and esc["escalated"] is True
    assert esc["citations"] == []


# ---- Spec case 3: terminal trace visibility ----
def test_trace_prints_sections_in_order_and_writes_log(capsys, tmp_path):
    log = tmp_path / "trace.log"
    r = format_response("1. Do X. [Article: KB0000001]", CHUNKS)
    print_execution_trace(INCIDENT, CHUNKS, r, confidence=0.5058, log_file=log)
    out = capsys.readouterr().out
    a = out.index("INCIDENT DETAILS")
    b = out.index("RETRIEVED CHUNKS & SCORES")
    c = out.index("FINAL STRUCTURED ANSWER")
    assert a < b < c
    assert "0.5058" in out and "KB0000001" in out
    assert "FINAL STRUCTURED ANSWER" in log.read_text(encoding="utf-8")