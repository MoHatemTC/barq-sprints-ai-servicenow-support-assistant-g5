"""Run the full RAG evaluation with one command.

    uv run python -m eval.run_rag_eval                 # snapshot mode (offline, default)
    uv run python -m eval.run_rag_eval --mode live     # live Qdrant + agent
    uv run python -m eval.run_rag_eval --no-llm        # deterministic metrics only (no judge calls)
    uv run python -m eval.run_rag_eval --check-judge   # test the judge connection and exit

Writes eval/reports/rag_report.md and rag_report.json.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # allow `python eval/run_rag_eval.py`
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")      # no usage data leaves this machine

import argparse
import hashlib
import json
import re
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import yaml
from dotenv import load_dotenv

from eval.adapters import AnswerResult, LiveAdapter, RagAdapter, RetrievedChunk, SnapshotAdapter
from eval.dataset import case_query, dataset_sha256, load_dataset
from eval.hit_at_k import first_hit_rank, hit_at_k, hit_rate

CITATION = re.compile(r"\[Article:\s*(KB\d{7})\]")
GEVAL_STEPS = [
    "The output must be a numbered procedure: lines starting with '1.', '2.', '3.' and so on, with at least two steps. "
    "Bullets, plain paragraphs or a single sentence do not count as a numbered procedure.",
    "Every step must name its source article with a citation of the form [Article: KB0010174] (the KB number will differ). "
    "Steps without a citation, or citations in another format, lower the score.",
    "The steps must be concrete actions the user or technician can perform, not vague advice.",
    "Score high only when BOTH the numbered structure and the per-step article citations are present.",
]


# --------------------------------------------------------------------------- #
# Config / adapter
# --------------------------------------------------------------------------- #
def load_config(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def make_adapter(mode: str, cfg: dict) -> RagAdapter:
    return LiveAdapter() if mode == "live" else SnapshotAdapter(cfg["paths"]["snapshot"])


# --------------------------------------------------------------------------- #
# DeepEval
# --------------------------------------------------------------------------- #
def build_metrics(cfg: dict, judge) -> dict[str, dict]:
    """Fresh metric objects (they keep per-case state, so never share across threads)."""
    from deepeval.metrics import (AnswerRelevancyMetric, ContextualPrecisionMetric, ContextualRecallMetric,
                                  ContextualRelevancyMetric, FaithfulnessMetric, GEval)
    try:
        from deepeval.test_case import SingleTurnParams as Params
    except ImportError:  # older DeepEval
        from deepeval.test_case import LLMTestCaseParams as Params

    t = cfg["thresholds"]
    kw = dict(model=judge, async_mode=False)
    return {
        "retrieval": {
            "contextual_precision": ContextualPrecisionMetric(threshold=t["contextual_precision"], **kw),
            "contextual_recall": ContextualRecallMetric(threshold=t["contextual_recall"], **kw),
            "contextual_relevancy": ContextualRelevancyMetric(threshold=t["contextual_relevancy"], **kw),
        },
        "generation": {
            "faithfulness": FaithfulnessMetric(threshold=t["faithfulness"], **kw),
            "answer_relevancy": AnswerRelevancyMetric(threshold=t["answer_relevancy"], **kw),
            "procedure_citation": GEval(
                name="Numbered Procedure With Article Citations",
                evaluation_steps=GEVAL_STEPS,
                evaluation_params=[Params.ACTUAL_OUTPUT],
                threshold=t["procedure_citation"], **kw),
        },
    }


def _measure(metric, test_case) -> dict:
    try:
        metric.measure(test_case)
        return {"score": round(float(metric.score), 4), "success": bool(metric.is_successful()),
                "reason": getattr(metric, "reason", None), "error": None}
    except Exception as exc:  # reported, never hidden
        return {"score": None, "success": False, "reason": None, "error": f"{type(exc).__name__}: {exc}"}


def run_deepeval(case: dict, query: str, retrieved: list[RetrievedChunk], answer: AnswerResult, cfg: dict, judge) -> dict:
    from deepeval.test_case import LLMTestCase

    metrics = build_metrics(cfg, judge)
    out: dict[str, dict] = {}
    top_k_texts = [c.text for c in retrieved]

    if case["category"] == "answerable":      # retrieval quality is only meaningful when an answer exists
        # Citation tags are NOT in the KB text, so a judge would call those words "unsupported by the
        # context" and wrongly lower contextual recall. Citations are checked by the G-Eval metric instead.
        expected_plain = re.sub(r"\s*\[Article:\s*KB\d{7}\]", "", case["expected_answer"]).strip()
        tc = LLMTestCase(input=query, actual_output=answer.text or "(no answer: escalated)",
                         expected_output=expected_plain, retrieval_context=top_k_texts)
        for name, m in metrics["retrieval"].items():
            out[name] = _measure(m, tc)

    if answer.answered:                        # generation metrics need an actual answer
        used = [c.text for c in answer.retrieved_chunks] or top_k_texts
        tc = LLMTestCase(input=query, actual_output=answer.text, retrieval_context=used)
        for name, m in metrics["generation"].items():
            out[name] = _measure(m, tc)
    return out


# --------------------------------------------------------------------------- #
# Deterministic analysis
# --------------------------------------------------------------------------- #
def citation_check(answer: AnswerResult) -> dict | None:
    """Non-LLM: every cited article must be one the agent actually retrieved."""
    if not answer.answered:
        return None
    cited = sorted(set(CITATION.findall(answer.text)))
    seen = {c.doc_id for c in answer.retrieved_chunks}
    return {"cited": cited, "valid": bool(cited) and set(cited) <= seen}


def separation_stats(answerable: list[float], unanswerable: list[float]) -> dict:
    """How well does the top retrieval score separate answerable from unanswerable incidents?"""
    def desc(xs):
        return {"n": len(xs), "mean": round(statistics.fmean(xs), 4), "median": round(statistics.median(xs), 4),
                "min": round(min(xs), 4), "max": round(max(xs), 4)} if xs else {"n": 0}

    pairs = [(a, u) for a in answerable for u in unanswerable]
    auc = (sum(1.0 if a > u else 0.5 if a == u else 0.0 for a, u in pairs) / len(pairs)) if pairs else None
    sweep = []
    for i in range(20, 91, 5):
        t = i / 100
        ans_ok = sum(s >= t for s in answerable) / len(answerable) if answerable else 0.0
        unans_ok = sum(s < t for s in unanswerable) / len(unanswerable) if unanswerable else 0.0
        sweep.append({"threshold": t, "answerable_kept": round(ans_ok, 3), "unanswerable_rejected": round(unans_ok, 3),
                      "balanced_accuracy": round((ans_ok + unans_ok) / 2, 3)})
    best = None
    if sweep:  # several thresholds can tie; take the middle of the plateau (most robust)
        top = max(r["balanced_accuracy"] for r in sweep)
        plateau = [r for r in sweep if r["balanced_accuracy"] == top]
        best = plateau[len(plateau) // 2]
    return {"answerable": desc(answerable), "unanswerable": desc(unanswerable),
            "auc": None if auc is None else round(auc, 3), "sweep": sweep, "best_threshold": best}


def at_threshold(sweep_scores_a: list[float], sweep_scores_u: list[float], t: float) -> dict:
    return {"threshold": t,
            "answerable_kept": round(sum(s >= t for s in sweep_scores_a) / len(sweep_scores_a), 3) if sweep_scores_a else None,
            "unanswerable_rejected": round(sum(s < t for s in sweep_scores_u) / len(sweep_scores_u), 3) if sweep_scores_u else None}


# --------------------------------------------------------------------------- #
# Per-case work
# --------------------------------------------------------------------------- #
def gather(case: dict, adapter: RagAdapter, cfg: dict) -> dict:
    query = case_query(case)
    retrieved = adapter.retrieve(query, cfg["retrieval"]["top_k"])
    answer = adapter.generate_answer(case["short_description"], case.get("description", ""))
    ids = [c.doc_id for c in retrieved]
    k, dedupe = cfg["retrieval"]["hit_k"], cfg["retrieval"]["dedupe_docs"]
    return {
        "id": case["id"], "category": case["category"], "language": case["language"], "difficulty": case["difficulty"],
        "query": query, "expected_answer": case["expected_answer"], "expected_ids": case["expected_article_ids"], "confusable_ids": case["confusable_article_ids"],
        "retrieved_ids": ids, "retrieved_scores": [round(c.score, 4) for c in retrieved],
        "best_score": max((c.score for c in retrieved), default=0.0),
        "agent_best_score": answer.max_score,  # best score seen by the agent's OWN searches (drives answer/escalate)
        "hit": hit_at_k(ids, case["expected_article_ids"], k, dedupe) if case["expected_article_ids"] else None,
        "rank": first_hit_rank(ids, case["expected_article_ids"], dedupe) if case["expected_article_ids"] else None,
        "outcome": answer.outcome, "answered": answer.answered, "answer_text": answer.text,
        "escalation_reason": answer.reason, "citations": citation_check(answer),
        "_retrieved": retrieved, "_answer": answer,
    }


def cache_key(row: dict, judge_name: str) -> str:
    blob = json.dumps(["v2-plain-expected", row["id"], row["query"], row["answer_text"], row["expected_answer"],
                       row["retrieved_ids"], row["retrieved_scores"], judge_name],
                      ensure_ascii=False)
    return hashlib.sha1(blob.encode()).hexdigest()


# --------------------------------------------------------------------------- #
# Aggregation + report
# --------------------------------------------------------------------------- #
def aggregate(rows: list[dict], cfg: dict, llm_ran: bool) -> dict:
    t = cfg["thresholds"]
    summary: dict = {}
    hr = hit_rate([{"id": r["id"], "retrieved_ids": r["retrieved_ids"], "expected_ids": r["expected_ids"]} for r in rows],
                  cfg["retrieval"]["hit_k"], cfg["retrieval"]["dedupe_docs"])
    summary["hit_at_3"] = {"value": round(hr["rate"], 4), "hits": hr["hits"], "total": hr["total"],
                           "threshold": t["hit_at_3"], "pass": hr["rate"] >= t["hit_at_3"]}
    by_lang = {}
    for lang_group, langs in {"english": {"en"}, "arabic_or_mixed": {"ar", "mixed"}}.items():
        sub = [r for r in rows if r["language"] in langs and r["expected_ids"]]
        by_lang[lang_group] = {"hits": sum(bool(r["hit"]) for r in sub), "total": len(sub)}
    summary["hit_at_3_by_language"] = by_lang

    unans = [r for r in rows if r["category"] == "unanswerable"]
    ans = [r for r in rows if r["category"] == "answerable"]
    refused = sum(not r["answered"] for r in unans)
    summary["refusal_rate"] = {"value": round(refused / len(unans), 4) if unans else None, "correct": refused,
                               "total": len(unans), "threshold": t["refusal_rate"],
                               "pass": bool(unans) and refused / len(unans) >= t["refusal_rate"]}
    false_ref = sum(not r["answered"] for r in ans)
    summary["false_refusal_rate"] = {"value": round(false_ref / len(ans), 4) if ans else None, "count": false_ref, "total": len(ans)}
    cites = [r["citations"] for r in rows if r["citations"]]
    summary["citation_grounded"] = {"value": round(sum(c["valid"] for c in cites) / len(cites), 4) if cites else None,
                                    "valid": sum(c["valid"] for c in cites), "total": len(cites)}

    if llm_ran:
        metrics = {}
        for name in ["contextual_precision", "contextual_recall", "contextual_relevancy",
                     "faithfulness", "answer_relevancy", "procedure_citation"]:
            results = [r["deepeval"][name] for r in rows if name in r.get("deepeval", {})]
            scored = [x["score"] for x in results if x["score"] is not None]
            metrics[name] = {"mean": round(statistics.fmean(scored), 4) if scored else None, "n": len(results),
                             "errors": sum(x["error"] is not None for x in results),
                             "case_pass_rate": round(sum(x["success"] for x in results) / len(results), 4) if results else None,
                             "threshold": t[name],
                             "pass": bool(scored) and statistics.fmean(scored) >= t[name]}
        summary["deepeval"] = metrics

    sa = [r["best_score"] for r in ans]
    su = [r["best_score"] for r in unans]
    summary["separation"] = separation_stats(sa, su)
    prod_t = float(os.getenv("SCORE_THRESHOLD", "0.70"))
    summary["separation"]["at_production_threshold"] = at_threshold(sa, su, prod_t)
    # same analysis on the scores the agent itself saw (its own search queries differ from the raw incident text)
    aa = [r["agent_best_score"] for r in ans]
    au = [r["agent_best_score"] for r in unans]
    summary["separation_agent"] = separation_stats(aa, au)
    summary["separation_agent"]["at_production_threshold"] = at_threshold(aa, au, prod_t)
    return summary


def fmt(x, nd=3):
    return "n/a" if x is None else f"{x:.{nd}f}"


def failing_cases(rows: list[dict], cfg: dict) -> list[dict]:
    out = []
    for r in rows:
        why = []
        if r["category"] == "answerable":
            if r["hit"] is False:
                why.append(f"Hit@3 miss (expected {', '.join(r['expected_ids'])}; top: {', '.join(dict.fromkeys(r['retrieved_ids']))[:60]})")
            if not r["answered"]:
                why.append(f"escalated instead of answering (best score {r['best_score']:.2f})")
        elif r["answered"]:
            why.append(f"answered an unanswerable incident (best score {r['best_score']:.2f})")
        for name, res in r.get("deepeval", {}).items():
            if res["error"]:
                why.append(f"{name}: ERROR")
            elif not res["success"]:
                why.append(f"{name}={res['score']:.2f} < {cfg['thresholds'][name]}")
        if r["citations"] and not r["citations"]["valid"]:
            why.append("cites an article it did not retrieve (or no citation)")
        if why:
            out.append({"id": r["id"], "category": r["category"], "language": r["language"], "reasons": why})
    return out


def write_reports(rows, summary, meta, cfg, llm_ran):
    out_dir = Path(cfg["paths"]["report_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    clean = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    fails = failing_cases(rows, cfg)
    (out_dir / cfg["paths"]["report_json"]).write_text(
        json.dumps({"meta": meta, "summary": summary, "failing_cases": fails, "cases": clean}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    s, L = summary, []
    L += ["# RAG Evaluation Report", "",
          f"- Generated: {meta['generated_at']}", f"- Mode: **{meta['adapter'].get('mode')}**",
          f"- Cases: {meta['cases']} ({meta['answerable']} answerable, {meta['unanswerable']} unanswerable)",
          f"- Dataset sha256: `{meta['dataset_sha256'][:12]}`",
          f"- Embedding model: `{meta['adapter'].get('embedding_model')}` | Agent LLM: `{meta['adapter'].get('llm_model')}` | Judge: `{meta.get('judge_model') or 'not run'}`",
          f"- Production score threshold: {meta['adapter'].get('score_threshold')} | top_k: {cfg['retrieval']['top_k']}", "",
          "## Summary", "", "| Metric | Result | Threshold | Status |", "|---|---|---|---|"]
    h = s["hit_at_3"]
    L.append(f"| Hit@3 (deterministic) | {fmt(h['value'])} ({h['hits']}/{h['total']}) | {h['threshold']} | {'PASS' if h['pass'] else 'FAIL'} |")
    r = s["refusal_rate"]
    L.append(f"| Refusal on unanswerable | {fmt(r['value'])} ({r['correct']}/{r['total']}) | {r['threshold']} | {'PASS' if r['pass'] else 'FAIL'} |")
    if llm_ran:
        for name, m in s["deepeval"].items():
            note = f" ({m['errors']} errors)" if m["errors"] else ""
            L.append(f"| {name} | {fmt(m['mean'])} mean over {m['n']}{note} | {m['threshold']} | {'PASS' if m['pass'] else 'FAIL'} |")
    else:
        L.append("| DeepEval metrics | skipped (`--no-llm`) | | |")
    L += ["", f"False refusals (answerable but escalated): {s['false_refusal_rate']['count']}/{s['false_refusal_rate']['total']}. "
          f"Citations pointing only to retrieved articles: {s['citation_grounded']['valid']}/{s['citation_grounded']['total']}.", "",
          "Hit@3 by language: " + "; ".join(f"{k} {v['hits']}/{v['total']}" for k, v in s["hit_at_3_by_language"].items()) + ".", ""]

    sep = s["separation"]
    L += ["## Score separation (top retrieval score)", "", "| Group | n | mean | median | min | max |", "|---|---|---|---|---|---|"]
    for g in ("answerable", "unanswerable"):
        d = sep[g]
        if d["n"]:
            L.append(f"| {g} | {d['n']} | {d['mean']} | {d['median']} | {d['min']} | {d['max']} |")
    pt = sep["at_production_threshold"]
    L += ["", f"AUC (probability an answerable incident outscores an unanswerable one): **{sep['auc']}**. "
          f"At the production threshold {pt['threshold']}: {fmt(pt['answerable_kept'])} of answerable kept, "
          f"{fmt(pt['unanswerable_rejected'])} of unanswerable rejected.", "",
          "| Threshold | Answerable kept | Unanswerable rejected | Balanced accuracy |", "|---|---|---|---|"]
    for row in sep["sweep"]:
        mark = " **<- best**" if sep["best_threshold"] and row["threshold"] == sep["best_threshold"]["threshold"] else ""
        L.append(f"| {row['threshold']:.2f} | {row['answerable_kept']} | {row['unanswerable_rejected']} | {row['balanced_accuracy']}{mark} |")

    sag = s["separation_agent"]
    L += ["", "### Same analysis on the scores the agent itself saw", "",
          "The agent writes its own search queries, so the best score it saw (which decides answer vs escalate) differs from the raw-incident score above.", "",
          "| Group | n | mean | median | min | max |", "|---|---|---|---|---|---|"]
    for g in ("answerable", "unanswerable"):
        d = sag[g]
        if d["n"]:
            L.append(f"| {g} | {d['n']} | {d['mean']} | {d['median']} | {d['min']} | {d['max']} |")
    pa = sag["at_production_threshold"]
    bt = sag["best_threshold"]
    L += ["", f"AUC: **{sag['auc']}**. At {pa['threshold']}: answerable kept {fmt(pa['answerable_kept'])}, unanswerable rejected {fmt(pa['unanswerable_rejected'])}."
          + (f" Best threshold in the sweep: **{bt['threshold']:.2f}** (balanced accuracy {bt['balanced_accuracy']}; "
             f"answerable kept {bt['answerable_kept']}, unanswerable rejected {bt['unanswerable_rejected']})." if bt else "")]

    L += ["", "## Failing or flagged cases", ""]
    if fails:
        L += ["| Case | Type | Lang | Problems |", "|---|---|---|---|"]
        L += [f"| {f['id']} | {f['category']} | {f['language']} | {'; '.join(f['reasons'])} |" for f in fails]
    else:
        L.append("None.")

    L += ["", "## All cases", "", "| Case | Type | Lang | Expected | Top-3 articles | Rank | Best score | Outcome |", "|---|---|---|---|---|---|---|---|"]
    for x in rows:
        top3 = ", ".join(list(dict.fromkeys(x["retrieved_ids"]))[:3])
        L.append(f"| {x['id']} | {x['category']} | {x['language']} | {', '.join(x['expected_ids']) or '-'} | {top3} | {x['rank'] or '-'} | {x['best_score']:.2f} | {x['outcome']} |")
    (out_dir / cfg["paths"]["report_md"]).write_text("\n".join(L) + "\n", encoding="utf-8")
    return fails


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(argv=None, judge=None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="eval/config.yaml")
    p.add_argument("--mode", choices=["snapshot", "live"], default="snapshot")
    p.add_argument("--no-llm", action="store_true", help="skip DeepEval (deterministic metrics only)")
    p.add_argument("--check-judge", action="store_true", help="send one test prompt to the judge and exit")
    p.add_argument("--no-cache", action="store_true", help="ignore cached DeepEval results")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--strict", action="store_true", help="exit 1 when any threshold fails")
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    if args.check_judge:
        from eval.judge import build_judge
        j = judge or build_judge(cfg)
        print(f"Judge model: {j.get_model_name()}\nReply: {j.generate('Reply with the single word: ready')!r}")
        return 0

    cases = load_dataset(cfg["paths"]["dataset"])[: args.limit]
    adapter = make_adapter(args.mode, cfg)
    print(f"Mode={args.mode} cases={len(cases)} top_k={cfg['retrieval']['top_k']}")
    if args.mode == "snapshot":
        snap_sha = adapter.meta.get("dataset_sha256")
        if snap_sha and snap_sha != dataset_sha256(cfg["paths"]["dataset"]):
            print("WARNING: dataset changed since the snapshot was recorded; unmatched cases will fail loudly.")

    rows = []
    for i, case in enumerate(cases, 1):
        row = gather(case, adapter, cfg)
        rows.append(row)
        print(f"[{i}/{len(cases)}] {row['id']} hit={row['hit']} outcome={row['outcome']} best={row['best_score']:.2f}")

    llm_ran = not args.no_llm
    judge_name = None
    if llm_ran:
        from eval.judge import build_judge
        judge = judge or build_judge(cfg)
        judge_name = judge.get_model_name()
        cache_path = Path(cfg["paths"]["report_dir"]) / "deepeval_cache.json"
        cache = {}
        if not args.no_cache and cache_path.exists():
            try:
                cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except ValueError:
                print(f"WARNING: {cache_path} is empty or corrupt; ignoring it.")
        lock = threading.Lock()
        todo = []
        for row, case in zip(rows, cases):
            key = cache_key(row, judge_name)
            row["_key"] = key
            if key in cache:
                row["deepeval"] = cache[key]
            else:
                todo.append((row, case))
        print(f"DeepEval judge={judge_name}: {len(rows) - len(todo)} cached, {len(todo)} to run "
              f"(concurrency {cfg['judge']['max_concurrency']})")

        def work(pair):
            row, case = pair
            return row, run_deepeval(case, row["query"], row["_retrieved"], row["_answer"], cfg, judge)

        with ThreadPoolExecutor(max_workers=int(cfg["judge"]["max_concurrency"])) as pool:
            futures = [pool.submit(work, pair) for pair in todo]
            for done, fut in enumerate(as_completed(futures), 1):
                row, res = fut.result()
                row["deepeval"] = res
                errs = sum(1 for v in res.values() if v["error"])
                with lock:
                    if not errs:  # never cache failures
                        cache[row["_key"]] = res
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    tmp = cache_path.with_suffix(".tmp")
                    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                    tmp.replace(cache_path)
                print(f"  judged {done}/{len(todo)} {row['id']}" + (f"  ({errs} metric errors)" if errs else ""))

    summary = aggregate(rows, cfg, llm_ran)
    meta = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "adapter": adapter.describe(),
            "cases": len(rows), "answerable": sum(r["category"] == "answerable" for r in rows),
            "unanswerable": sum(r["category"] == "unanswerable" for r in rows),
            "dataset_sha256": dataset_sha256(cfg["paths"]["dataset"]), "judge_model": judge_name,
            "thresholds": cfg["thresholds"]}
    fails = write_reports(rows, summary, meta, cfg, llm_ran)

    print("\n=== SUMMARY ===")
    h = summary["hit_at_3"]
    print(f"Hit@3: {h['value']:.3f} ({h['hits']}/{h['total']}) threshold {h['threshold']} -> {'PASS' if h['pass'] else 'FAIL'}")
    rr = summary["refusal_rate"]
    print(f"Refusal on unanswerable: {fmt(rr['value'])} ({rr['correct']}/{rr['total']}) -> {'PASS' if rr['pass'] else 'FAIL'}")
    all_pass = h["pass"] and rr["pass"]
    errors = 0
    if llm_ran:
        for name, m in summary["deepeval"].items():
            print(f"{name}: {fmt(m['mean'])} threshold {m['threshold']} -> {'PASS' if m['pass'] else 'FAIL'}"
                  + (f"  [{m['errors']} errors]" if m["errors"] else ""))
            all_pass &= m["pass"]
            errors += m["errors"]
    print(f"Separation AUC: {summary['separation']['auc']} | flagged cases: {len(fails)}")
    print(f"Reports: {Path(cfg['paths']['report_dir']) / cfg['paths']['report_md']} and {cfg['paths']['report_json']}")
    print("Run complete.")
    if errors:
        print(f"{errors} metric evaluations errored; fix the judge connection and re-run (successful results are cached).")
        return 1
    return 0 if (all_pass or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())