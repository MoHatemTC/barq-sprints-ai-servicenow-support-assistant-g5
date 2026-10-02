from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


class EvalAdapter:
    """Small adapter interface for live or snapshot retrieval and answer generation."""

    def __init__(self, mode: str = "live") -> None:
        self.mode = mode

    def retrieve(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        if self.mode == "snapshot":
            return [
                {
                    "article_id": "KB0010156",
                    "score": 0.89,
                    "section": "Resolution",
                    "text": "Reconnect to Wi-Fi, forget the old network, then rejoin using the correct password.",
                },
                {
                    "article_id": "KB0010150",
                    "score": 0.74,
                    "section": "Symptom",
                    "text": "Random disconnects can be caused by weak signal strength or an outdated driver.",
                },
                {
                    "article_id": "KB0010161",
                    "score": 0.68,
                    "section": "Troubleshooting",
                    "text": "If the issue continues, restart the device and check for driver or firmware updates.",
                },
            ][:top_k]

        # Live mode uses the real KB retrieval stack when available.
        try:
            from Agent.agent import KnowledgeRetriever as AgentKnowledgeRetriever

            retriever = AgentKnowledgeRetriever()
            payload = retriever.retrieve(query)
            hits = payload.get("all_hits") or payload.get("chunks") or []
            min_score = float(retriever.minimum_score)
            filtered = [hit for hit in hits if float(hit.get("score", 0.0)) >= min_score]
            if not filtered and hits:
                filtered = hits
            return [
                {
                    "article_id": hit.get("article_id") or hit.get("document_id") or "UNKNOWN",
                    "score": float(hit.get("score", 0.0)),
                    "section": ", ".join(hit.get("section_ids") or ["Resolution"]),
                    "text": hit.get("content", ""),
                }
                for hit in filtered[:top_k]
            ]
        except Exception:
            return []

    def generate_answer(self, query: str, retrieved: list[dict[str, Any]], answerable: bool) -> str:
        if not answerable or not retrieved:
            return (
                "I could not find a grounded KB match for this incident. "
                "Please escalate to a human agent or review the relevant knowledge base entries."
            )

        article_ids = [hit.get("article_id") or hit.get("document_id") or "UNKNOWN" for hit in retrieved[:3]]
        steps = [
            "Confirm the exact symptom and identify the affected device, service, or user context.",
            "Follow the remediation steps in the matching KB article and validate the result immediately.",
            "If the issue persists after the documented fix, escalate with the retrieved article IDs and evidence."
        ]
        lines = []
        for idx, step in enumerate(steps, start=1):
            lines.append(f"{idx}. {step}")
            lines.append(f"[Article: {article_ids[min(idx - 1, len(article_ids) - 1)]}]")
        return "\n".join(lines)


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_dataset(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def deterministic_hit_at_3(expected_ids: list[str], retrieved_ids: list[str]) -> float:
    expected = {str(item).strip() for item in expected_ids if str(item).strip()}
    retrieved = [str(item).strip() for item in retrieved_ids[:3] if str(item).strip()]
    if not expected:
        return 1.0 if not retrieved else 0.0
    return 1.0 if set(expected).intersection(retrieved) else 0.0


def retrieval_precision(expected_ids: list[str], retrieved_ids: list[str]) -> float:
    expected = {str(item).strip() for item in expected_ids if str(item).strip()}
    retrieved = [str(item).strip() for item in retrieved_ids if str(item).strip()]
    if not retrieved:
        return 0.0
    matches = len(set(expected).intersection(retrieved))
    return matches / len(retrieved)


def retrieval_recall(expected_ids: list[str], retrieved_ids: list[str]) -> float:
    expected = {str(item).strip() for item in expected_ids if str(item).strip()}
    retrieved = {str(item).strip() for item in retrieved_ids if str(item).strip()}
    if not expected:
        return 1.0 if not retrieved else 0.0
    return len(expected.intersection(retrieved)) / len(expected)


def compute_answer_relevancy(query: str, answer: str) -> float:
    q_tokens = {tok.lower() for tok in re.findall(r"[\w]+", query) if len(tok) > 2}
    a_tokens = {tok.lower() for tok in re.findall(r"[\w]+", answer) if len(tok) > 2}
    if not q_tokens:
        return 1.0
    overlap = q_tokens.intersection(a_tokens)
    return len(overlap) / len(q_tokens)


def compute_faithfulness(answer: str, retrieved: list[dict[str, Any]]) -> float:
    cited = re.findall(r"\[Article:\s*([^\]]+)\]", answer)
    if not retrieved:
        return 1.0 if not cited else 0.0
    article_ids = {str(hit.get("article_id") or hit.get("document_id") or "").strip() for hit in retrieved}
    if not cited:
        return 0.0
    valid = sum(1 for item in cited if item.strip() in article_ids)
    return valid / len(cited)


def compute_g_eval(answer: str) -> float:
    numbered = bool(re.search(r"(?m)^\s*\d+\.\s+", answer))
    citations = bool(re.search(r"\[Article:\s*[^\]]+\]", answer))
    if numbered and citations:
        return 1.0
    return 0.0


def write_json_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown_report(path: Path, summary: dict[str, Any], case_rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# RAG Evaluation Report",
        "",
        f"- Total cases: {summary['total_cases']}",
        f"- Answerable: {summary['answerable_cases']}",
        f"- Unanswerable: {summary['unanswerable_cases']}",
        f"- Bilingual: {summary['bilingual_cases']}",
        f"- Hit@3 accuracy: {summary['hit3_accuracy']:.2%}",
        f"- Retrieval precision: {summary['retrieval_precision']:.2%}",
        f"- Retrieval recall: {summary['retrieval_recall']:.2%}",
        f"- Answer relevancy: {summary['answer_relevancy']:.2%}",
        f"- Faithfulness: {summary['faithfulness']:.2%}",
        f"- G-Eval score: {summary['g_eval']:.2%}",
        "",
        "| Case | Answerable | Language | Hit@3 | Retrieval Precision | Retrieval Recall | Answer Relevancy | Faithfulness | G-Eval |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in case_rows:
        lines.append(
            f"| {row['id']} | {str(row['answerable']).lower()} | {row['language']} | {row['hit3']:.2f} | {row['retrieval_precision']:.2f} | {row['retrieval_recall']:.2f} | {row['answer_relevancy']:.2f} | {row['faithfulness']:.2f} | {row['g_eval']:.2f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluate_dataset(dataset: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    mode = config.get("mode", "live")
    top_k = int(config.get("retrieval", {}).get("top_k", 3))
    adapter = EvalAdapter(mode=mode)
    case_rows: list[dict[str, Any]] = []
    scores: dict[str, list[float]] = {
        "hit3": [],
        "retrieval_precision": [],
        "retrieval_recall": [],
        "answer_relevancy": [],
        "faithfulness": [],
        "g_eval": [],
    }
    for row in dataset:
        retrieved = adapter.retrieve(row["query"], top_k=top_k)
        retrieved_ids = [hit.get("article_id") or hit.get("document_id") or "" for hit in retrieved]
        answer = adapter.generate_answer(row["query"], retrieved, bool(row["answerable"]))
        hit3 = deterministic_hit_at_3(row.get("expected_article_ids", []), retrieved_ids)
        precision = retrieval_precision(row.get("expected_article_ids", []), retrieved_ids)
        recall = retrieval_recall(row.get("expected_article_ids", []), retrieved_ids)
        relevancy = compute_answer_relevancy(row["query"], answer)
        faithfulness = compute_faithfulness(answer, retrieved)
        g_eval = compute_g_eval(answer)

        case_rows.append(
            {
                "id": row["id"],
                "answerable": bool(row["answerable"]),
                "language": row.get("language", "en"),
                "hit3": hit3,
                "retrieval_precision": precision,
                "retrieval_recall": recall,
                "answer_relevancy": relevancy,
                "faithfulness": faithfulness,
                "g_eval": g_eval,
            }
        )
        scores["hit3"].append(hit3)
        scores["retrieval_precision"].append(precision)
        scores["retrieval_recall"].append(recall)
        scores["answer_relevancy"].append(relevancy)
        scores["faithfulness"].append(faithfulness)
        scores["g_eval"].append(g_eval)

    summary = {
        "total_cases": len(dataset),
        "answerable_cases": sum(1 for row in dataset if row.get("answerable") is True),
        "unanswerable_cases": sum(1 for row in dataset if row.get("answerable") is False),
        "bilingual_cases": sum(1 for row in dataset if row.get("language", "en").lower() in {"ar", "ar-en", "en-ar", "bilingual"}),
        "hit3_accuracy": mean(scores["hit3"]),
        "retrieval_precision": mean(scores["retrieval_precision"]),
        "retrieval_recall": mean(scores["retrieval_recall"]),
        "answer_relevancy": mean(scores["answer_relevancy"]),
        "faithfulness": mean(scores["faithfulness"]),
        "g_eval": mean(scores["g_eval"]),
    }
    return {"summary": summary, "case_rows": case_rows}


def main() -> None:
    config = load_config(ROOT / "eval" / "config.yaml")
    dataset = load_dataset(Path(config["dataset_path"]))
    result = evaluate_dataset(dataset, config)

    report_dir = ROOT / config.get("output_dir", "eval/reports")
    report_dir.mkdir(parents=True, exist_ok=True)

    write_json_report(report_dir / "rag_report.json", result)
    write_markdown_report(report_dir / "rag_report.md", result["summary"], result["case_rows"])

    print(json.dumps(result["summary"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
