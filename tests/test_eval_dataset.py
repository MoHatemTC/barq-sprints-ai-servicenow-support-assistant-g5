"""Offline tests: golden dataset schema + deterministic Hit@k. No LLM, no network, no Qdrant."""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.hit_at_k import first_hit_rank, hit_at_k, hit_rate  # noqa: E402

DATASET = ROOT / "eval" / "datasets" / "rag_golden.json"
KB_INDEX = ROOT / "eval" / "datasets" / "kb_index.json"
ARABIC = re.compile(r"[\u0600-\u06FF]")
REQUIRED = {
    "id", "language", "category", "difficulty", "tags", "short_description", "description",
    "expected_article_ids", "primary_article_id", "confusable_article_ids",
    "expected_behavior", "expected_answer", "provenance",
}


@pytest.fixture(scope="module")
def cases():
    return json.loads(DATASET.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def kb():
    return {a["article_id"]: a["title"] for a in json.loads(KB_INDEX.read_text(encoding="utf-8"))}


# ----------------------------- dataset schema ------------------------------ #
def test_size_and_mix(cases):
    answerable = [c for c in cases if c["category"] == "answerable"]
    unanswerable = [c for c in cases if c["category"] == "unanswerable"]
    arabic = [c for c in cases if c["language"] in ("ar", "mixed")]
    assert len(cases) >= 20
    assert len(answerable) >= 15
    assert len(unanswerable) >= 3
    assert len(arabic) >= 2


def test_required_fields_and_unique_ids(cases):
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "duplicate case ids"
    for c in cases:
        assert REQUIRED <= set(c), f"{c.get('id')} missing {REQUIRED - set(c)}"
        assert c["category"] in {"answerable", "unanswerable"}
        assert c["language"] in {"en", "ar", "mixed"}
        assert c["difficulty"] in {"easy", "medium", "hard"}
        assert c["short_description"].strip()


def test_article_ids_exist_in_kb(cases, kb):
    for c in cases:
        for a in c["expected_article_ids"] + c["confusable_article_ids"]:
            assert a in kb, f"{c['id']} references unknown article {a}"


def test_answerable_cases(cases):
    for c in (c for c in cases if c["category"] == "answerable"):
        assert c["expected_article_ids"], c["id"]
        assert c["primary_article_id"] in c["expected_article_ids"], c["id"]
        assert c["expected_behavior"] == "answer"
        assert re.search(r"(?m)^1\. ", c["expected_answer"]), f"{c['id']}: expected_answer must be numbered"
        cited = set(re.findall(r"\[Article: (KB\d{7})\]", c["expected_answer"]))
        assert cited and cited <= set(c["expected_article_ids"]), f"{c['id']}: bad citations"


def test_unanswerable_cases(cases):
    for c in (c for c in cases if c["category"] == "unanswerable"):
        assert c["expected_article_ids"] == [], c["id"]
        assert c["primary_article_id"] is None
        assert c["expected_behavior"] == "escalate"
        assert c["expected_answer"] == ""


def test_provenance_documented_and_not_title_copy(cases, kb):
    titles = {t.lower() for t in kb.values()}
    for c in cases:
        prov = c["provenance"]
        assert len(prov["derivation"].split()) >= 8, f"{c['id']}: provenance too thin"
        assert c["short_description"].strip().lower() not in titles, f"{c['id']} copies an article title"
        if c["category"] == "answerable":
            assert set(prov["source_steps"]) == set(c["expected_article_ids"]), c["id"]
            assert all(prov["source_steps"].values()), f"{c['id']}: source_steps empty"


def test_arabic_cases_contain_arabic_text(cases):
    for c in (c for c in cases if c["language"] in ("ar", "mixed")):
        assert ARABIC.search(c["short_description"] + c["description"]), c["id"]


def test_every_article_is_covered(cases, kb):
    covered = {a for c in cases for a in c["expected_article_ids"]}
    assert covered == set(kb), f"articles without a test case: {sorted(set(kb) - covered)}"


# ------------------------------ Hit@k logic -------------------------------- #
def test_hit_when_expected_in_top3():
    assert hit_at_k(["KB1", "KB3", "KB2"], ["KB3"]) is True


def test_miss_when_expected_at_rank_4():
    assert hit_at_k(["KB1", "KB2", "KB4", "KB3"], ["KB3"]) is False


def test_any_expected_id_counts():
    assert hit_at_k(["KB9", "KB2"], ["KB2", "KB7"]) is True


def test_empty_retrieval_is_a_miss():
    assert hit_at_k([], ["KB1"]) is False


def test_no_expected_ids_is_never_a_hit():
    assert hit_at_k(["KB1"], []) is False


def test_chunks_of_same_article_count_once():
    ranked = ["KB1", "KB1", "KB1", "KB2"]
    assert hit_at_k(ranked, ["KB2"], k=3, dedupe=True) is True    # KB1, KB2 are the top 2 articles
    assert hit_at_k(ranked, ["KB2"], k=3, dedupe=False) is False  # raw chunk positions: KB2 is 4th


def test_first_hit_rank():
    assert first_hit_rank(["KB1", "KB1", "KB2"], ["KB2"]) == 2
    assert first_hit_rank(["KB1"], ["KB2"]) is None


def test_hit_rate_ignores_unanswerable():
    cases = [
        {"id": "a", "retrieved_ids": ["KB1"], "expected_ids": ["KB1"]},
        {"id": "b", "retrieved_ids": ["KB5", "KB6", "KB7", "KB1"], "expected_ids": ["KB1"]},
        {"id": "c", "retrieved_ids": [], "expected_ids": []},           # unanswerable: skipped
    ]
    r = hit_rate(cases, k=3)
    assert (r["hits"], r["total"], r["rate"]) == (1, 2, 0.5)
    assert "c" not in r["per_case"]