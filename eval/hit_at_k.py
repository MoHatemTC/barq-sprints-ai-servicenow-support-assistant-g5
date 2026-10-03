"""Deterministic retrieval metric: Hit@k. No LLM, no network, fully repeatable.

A case is a HIT when at least one expected article ID appears among the first
k retrieved results. Only ANSWERABLE cases are scored here: unanswerable cases
have no expected article, so they are judged by refusal behaviour instead.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence


def _ranked_docs(retrieved_ids: Sequence[str], dedupe: bool) -> list[str]:
    """Ranked list of doc IDs. With dedupe=True several chunks of one article
    count once, so k means 'k distinct articles' (articles are split into many
    small chunks, so otherwise three chunks of one article would fill the top 3)."""
    if not dedupe:
        return list(retrieved_ids)
    seen: set[str] = set()
    ranked: list[str] = []
    for doc_id in retrieved_ids:
        if doc_id not in seen:
            seen.add(doc_id)
            ranked.append(doc_id)
    return ranked


def hit_at_k(retrieved_ids: Sequence[str], expected_ids: Iterable[str], k: int = 3, dedupe: bool = True) -> bool:
    expected = set(expected_ids)
    if not expected or k <= 0:
        return False
    return any(doc in expected for doc in _ranked_docs(retrieved_ids, dedupe)[:k])


def first_hit_rank(retrieved_ids: Sequence[str], expected_ids: Iterable[str], dedupe: bool = True) -> int | None:
    """1-based rank of the first expected article, or None. Useful for failure analysis."""
    expected = set(expected_ids)
    for rank, doc in enumerate(_ranked_docs(retrieved_ids, dedupe), start=1):
        if doc in expected:
            return rank
    return None


def hit_rate(cases: Sequence[dict], k: int = 3, dedupe: bool = True) -> dict:
    """cases: dicts with 'id', 'retrieved_ids' and 'expected_ids'.
    Cases with no expected IDs (unanswerable) are skipped, never counted as hits."""
    scored = [c for c in cases if c["expected_ids"]]
    per_case = {
        c["id"]: {
            "hit": hit_at_k(c["retrieved_ids"], c["expected_ids"], k, dedupe),
            "rank": first_hit_rank(c["retrieved_ids"], c["expected_ids"], dedupe),
        }
        for c in scored
    }
    hits = sum(1 for v in per_case.values() if v["hit"])
    return {
        "k": k,
        "hits": hits,
        "total": len(scored),
        "rate": (hits / len(scored)) if scored else 0.0,
        "per_case": per_case,
    }