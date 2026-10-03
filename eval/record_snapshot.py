"""Record live retrieval + agent answers into an offline snapshot fixture.

    uv run python -m eval.record_snapshot                # record missing cases
    uv run python -m eval.record_snapshot --force        # re-record everything
    uv run python -m eval.record_snapshot --limit 3      # quick smoke test

Needs the live stack (Qdrant, embedding model, LLM) and a populated .env.
Secrets are never written to the snapshot: only model names and settings.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .adapters import DEFAULT_SNAPSHOT, LiveAdapter
from eval.dataset import DEFAULT_DATASET, case_query, dataset_sha256, load_dataset


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default=str(DEFAULT_DATASET))
    p.add_argument("--out", default=str(DEFAULT_SNAPSHOT))
    p.add_argument("--top-k", type=int, default=int(os.getenv("TOP_K", "5")))
    p.add_argument("--force", action="store_true", help="re-record cases already in the snapshot")
    p.add_argument("--limit", type=int, default=None, help="only the first N cases")
    args = p.parse_args()

    cases = load_dataset(args.dataset)[: args.limit]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, dict] = {}
    if out.exists() and not args.force:
        existing = {e["query"]: e for e in json.loads(out.read_text(encoding="utf-8"))["entries"]}

    adapter = LiveAdapter()
    entries, errors = [], []
    for i, case in enumerate(cases, 1):
        query = case_query(case)
        if query in existing:
            entries.append(existing[query])
            print(f"[{i}/{len(cases)}] {case['id']} cached")
            continue
        try:
            retrieval = [asdict(c) for c in adapter.retrieve(query, args.top_k)]
            answer = asdict(adapter.generate_answer(case["short_description"], case.get("description", "")))
            entries.append({"case_id": case["id"], "query": query, "retrieval": retrieval, "answer": answer})
            print(f"[{i}/{len(cases)}] {case['id']} ok  top1={retrieval[0]['doc_id'] if retrieval else None} "
                  f"outcome={answer['outcome']}")
        except Exception as exc:  # keep going; report at the end
            errors.append((case["id"], f"{type(exc).__name__}: {exc}"))
            print(f"[{i}/{len(cases)}] {case['id']} FAILED {type(exc).__name__}: {exc}")

    meta = {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "top_k": args.top_k,
        "score_threshold": float(os.getenv("SCORE_THRESHOLD", "0.70")),
        "embedding_model": os.getenv("EMBEDDING_MODEL_NAME"),
        "llm_model": os.getenv("LLM_MODEL"),
        "dataset_sha256": dataset_sha256(args.dataset),
    }
    out.write_text(json.dumps({"meta": meta, "entries": entries}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {len(entries)} entries to {out}")
    if errors:
        print(f"{len(errors)} case(s) FAILED, re-run to retry only those:")
        for cid, msg in errors:
            print(f"  {cid}: {msg}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())