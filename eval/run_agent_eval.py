"""eval/run_agent_eval.py

CLI Evaluation Runner and CI Gating Harness for Sprint 4 Task S4.2.
Executes evaluation over agent scenarios (recorded or live mode),
computes deterministic checks and DeepEval G-Eval metrics,
generates a comprehensive Markdown report, and exits with non-zero
exit code upon any gating threshold breach.

Usage:
    python eval/run_agent_eval.py --mode recorded
    python eval/run_agent_eval.py --mode live --llm-judge
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Handle Windows case collision where git tracks both 'Agent' and 'agent'
if "agent" not in sys.modules:
    import importlib.util
    _agent_dir = PROJECT_ROOT / "agent"
    if not _agent_dir.exists():
        _agent_dir = PROJECT_ROOT / "Agent"
    if _agent_dir.exists() and (_agent_dir / "__init__.py").exists():
        _spec = importlib.util.spec_from_file_location(
            "agent",
            str(_agent_dir / "__init__.py"),
            submodule_search_locations=[str(_agent_dir)],
        )
        if _spec and _spec.loader:
            _mod = importlib.util.module_from_spec(_spec)
            sys.modules["agent"] = _mod
            sys.modules["Agent"] = _mod
            _spec.loader.exec_module(_mod)

# Ensure UTF-8 stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from eval.adapter import AgentAdapter, ExecutionTranscript
from eval.metrics import AgentEvaluator, MetricScore
from eval.validators import ValidationResult, run_all_deterministic_checks

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("eval.runner")


def load_yaml_config(config_path: str | Path) -> Dict[str, Any]:
    """Loads evaluation configuration YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_scenarios(dataset_path: str | Path) -> List[Dict[str, Any]]:
    """Loads evaluation scenarios dataset JSON file."""
    path = Path(dataset_path)
    if not path.exists():
        raise FileNotFoundError(f"Scenario dataset not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("scenarios", [])


def run_evaluation(
    mode: str = "recorded",
    config_path: str = "eval/agent_config.yaml",
    dataset_path: str | None = None,
    report_path: str | None = None,
    use_llm_judge: bool = False,
) -> int:
    """Main evaluation execution and gating logic."""
    print("=" * 80)
    print(f"[*] STARTING SPRINT 4 AGENT EVALUATION (Mode: {mode.upper()})")
    print("=" * 80)

    # 1. Load Config & Scenarios
    config = load_yaml_config(config_path)
    dataset_file = dataset_path or config.get("paths", {}).get("dataset", "eval/datasets/agent_scenarios.json")
    fixtures_file = config.get("paths", {}).get("fixtures", "eval/fixtures/agent_runs.json")
    report_file = report_path or config.get("paths", {}).get("report", "eval/reports/agent_report.md")

    scenarios = load_scenarios(dataset_file)
    logger.info("Loaded %d scenarios from %s", len(scenarios), dataset_file)

    adapter = AgentAdapter(fixtures_path=fixtures_file)
    evaluator = AgentEvaluator(config=config)

    # 2. Iterate Over Scenarios
    scenario_results: List[Dict[str, Any]] = []
    category_totals = defaultdict(int)
    category_passes = defaultdict(int)
    metric_scores_accum = defaultdict(list)
    deterministic_failures = 0

    max_iterations = int(config.get("agent_constraints", {}).get("max_iterations", 6))

    for idx, scn in enumerate(scenarios, start=1):
        scn_id = scn["id"]
        category = scn["category"]
        category_totals[category] += 1

        print(f"[{idx:02d}/{len(scenarios):02d}] Evaluating {scn_id} ({category}): {scn['title'][:45]}...", end=" ")

        # Run adapter
        try:
            transcript: ExecutionTranscript = adapter.run(scn, mode=mode)
        except Exception as exc:
            logger.error("Adapter failure on %s: %s", scn_id, exc)
            print("💥 ADAPTER ERROR")
            scenario_results.append({
                "scenario": scn,
                "passed": False,
                "error": f"Adapter error: {exc}",
                "deterministic_checks": {},
                "metric_scores": {},
            })
            continue

        # Deterministic checks
        det_results: Dict[str, ValidationResult] = run_all_deterministic_checks(
            transcript=transcript,
            scenario=scn,
            max_iterations=max_iterations,
        )
        all_det_passed = all(r.passed for r in det_results.values())
        if not all_det_passed:
            deterministic_failures += 1

        # DeepEval & G-Eval Metrics
        metrics: Dict[str, MetricScore] = evaluator.evaluate_transcript(
            transcript=transcript,
            scenario=scn,
            use_llm_judge=use_llm_judge,
        )
        all_metrics_passed = all(m.passed for m in metrics.values())
        for m_name, m_val in metrics.items():
            metric_scores_accum[m_name].append(m_val.score)

        # Scenario overall pass
        scenario_passed = all_det_passed and all_metrics_passed
        if scenario_passed:
            category_passes[category] += 1
            print("[PASS]")
        else:
            print("[FAIL]")
            failures = [f"{k}: {v.message}" for k, v in det_results.items() if not v.passed]
            failures += [f"{k}: {v.reason}" for k, v in metrics.items() if not v.passed]
            logger.warning("Failures for %s: %s", scn_id, failures)

        scenario_results.append({
            "scenario": scn,
            "transcript": transcript.to_dict(),
            "passed": scenario_passed,
            "deterministic_checks": {k: {"passed": v.passed, "message": v.message} for k, v in det_results.items()},
            "metric_scores": {k: {"score": v.score, "passed": v.passed, "reason": v.reason} for k, v in metrics.items()},
        })

    # 3. Aggregate Gating Metrics
    total_scenarios = len(scenarios)
    total_passed = sum(1 for r in scenario_results if r["passed"])
    overall_pass_rate = round(total_passed / total_scenarios, 4) if total_scenarios else 0.0

    gating_cfg = config.get("gating", {})
    required_overall = float(gating_cfg.get("overall_pass_rate", 0.85))
    required_det_rate = float(gating_cfg.get("deterministic_pass_rate", 1.0))
    cat_thresholds = gating_cfg.get("category_thresholds", {})

    det_pass_rate = round((total_scenarios - deterministic_failures) / total_scenarios, 4) if total_scenarios else 0.0

    # 4. Check Gating Breaches
    gating_breaches: List[str] = []

    if overall_pass_rate < required_overall:
        gating_breaches.append(
            f"Overall pass rate {overall_pass_rate:.1%} is below required threshold of {required_overall:.1%}"
        )

    if det_pass_rate < required_det_rate:
        gating_breaches.append(
            f"Deterministic structural checks pass rate {det_pass_rate:.1%} breached required zero-tolerance {required_det_rate:.1%}"
        )

    for cat, total in category_totals.items():
        passes = category_passes[cat]
        cat_rate = round(passes / total, 4) if total else 0.0
        req_cat_rate = float(cat_thresholds.get(cat, 0.80))
        if cat_rate < req_cat_rate:
            gating_breaches.append(
                f"Category '{cat}' pass rate {cat_rate:.1%} ({passes}/{total}) is below threshold {req_cat_rate:.1%}"
            )

    gating_passed = len(gating_breaches) == 0

    # 5. Print Scorecard Summary Table
    print("\n" + "=" * 80)
    print("EVALUATION SCORECARD SUMMARY")
    print("=" * 80)
    print(f"{'Category':<24} | {'Total':<6} | {'Passed':<6} | {'Pass Rate':<10} | {'Threshold':<10} | {'Status'}")
    print("-" * 80)
    for cat, total in category_totals.items():
        passes = category_passes[cat]
        cat_rate = passes / total if total else 0.0
        req_rate = float(cat_thresholds.get(cat, 0.80))
        status = "[PASS]" if cat_rate >= req_rate else "[BREACH]"
        print(f"{cat:<24} | {total:<6} | {passes:<6} | {cat_rate:<10.1%} | {req_rate:<10.1%} | {status}")
    print("-" * 80)
    overall_status = "[PASS]" if overall_pass_rate >= required_overall else "[BREACH]"
    print(f"{'OVERALL':<24} | {total_scenarios:<6} | {total_passed:<6} | {overall_pass_rate:<10.1%} | {required_overall:<10.1%} | {overall_status}")
    print("=" * 80)

    # 6. Generate Markdown Report
    _generate_markdown_report(
        report_file=report_file,
        mode=mode,
        total_scenarios=total_scenarios,
        total_passed=total_passed,
        overall_pass_rate=overall_pass_rate,
        required_overall=required_overall,
        category_totals=category_totals,
        category_passes=category_passes,
        cat_thresholds=cat_thresholds,
        metric_scores_accum=metric_scores_accum,
        gating_passed=gating_passed,
        gating_breaches=gating_breaches,
        scenario_results=scenario_results,
    )
    print(f"[REPORT] Full report saved to: {report_file}")

    # 7. Final Gating Verdict & Exit
    if gating_passed:
        print("\n[GATING] CI/CD GATING STATUS: PASSED (All thresholds satisfied)")
        print("=" * 80)
        return 0
    else:
        print("\n[GATING] CI/CD GATING STATUS: FAILED (Pipeline blocked by threshold breach)")
        for b in gating_breaches:
            print(f"   - {b}")
        print("=" * 80)
        return 1


def _generate_markdown_report(
    report_file: str,
    mode: str,
    total_scenarios: int,
    total_passed: int,
    overall_pass_rate: float,
    required_overall: float,
    category_totals: Dict[str, int],
    category_passes: Dict[str, int],
    cat_thresholds: Dict[str, float],
    metric_scores_accum: Dict[str, List[float]],
    gating_passed: bool,
    gating_breaches: List[str],
    scenario_results: List[Dict[str, Any]],
) -> None:
    """Generates the formal eval/reports/agent_report.md artifact."""
    out_path = Path(report_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    status_badge = "🟢 **PASSED**" if gating_passed else "🔴 **FAILED (GATING BREACH)**"

    lines = [
        "# Agent Behaviour & Safety Evaluation Report",
        "",
        f"**Sprint**: Sprint 4 (Trust & Hardening) · Task S4.2  ",
        f"**Date Generated**: {timestamp}  ",
        f"**Execution Mode**: `{mode}`  ",
        f"**Gating Result**: {status_badge}  ",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        "",
        f"- **Total Scenarios Evaluated**: {total_scenarios}",
        f"- **Total Scenarios Passed**: {total_passed}",
        f"- **Overall Pass Rate**: **{overall_pass_rate:.1%}** (Gating Threshold: `{required_overall:.1%}`)",
        f"- **Structural Deterministic Checks**: {'100% Passed' if not any('Deterministic' in b for b in gating_breaches) else 'Breached'}",
        "",
    ]

    if gating_breaches:
        lines.append("### ⚠️ Gating Breaches")
        for b in gating_breaches:
            lines.append(f"- ❌ {b}")
        lines.append("")

    lines += [
        "## 2. Category Performance Scorecard",
        "",
        "| Category | Scenarios | Passed | Pass Rate | Gating Threshold | Status |",
        "|---|:---:|:---:|:---:|:---:|:---:|",
    ]

    for cat, total in category_totals.items():
        passes = category_passes[cat]
        cat_rate = passes / total if total else 0.0
        req_rate = float(cat_thresholds.get(cat, 0.80))
        status = "✅ PASS" if cat_rate >= req_rate else "❌ BREACH"
        lines.append(f"| `{cat}` | {total} | {passes} | {cat_rate:.1%} | {req_rate:.1%} | {status} |")

    lines += [
        f"| **OVERALL** | **{total_scenarios}** | **{total_passed}** | **{overall_pass_rate:.1%}** | **{required_overall:.1%}** | **{status_badge}** |",
        "",
        "---",
        "",
        "## 3. DeepEval & G-Eval Metric Averages",
        "",
        "| Metric Name | Mean Score | Gating Threshold | Evaluation Focus |",
        "|---|:---:|:---:|---|",
    ]

    metric_desc = {
        "tool_correctness": "Tool selection trajectory matching expected tool order",
        "grounding": "Strict citation grounding against retrieved knowledge chunks",
        "safety_and_scope": "Prompt injection resistance and advisory role enforcement",
        "handoff_quality": "Clean escalation via requestHR without speculative guessing",
    }

    for m_name, scores in metric_scores_accum.items():
        avg = sum(scores) / len(scores) if scores else 0.0
        desc = metric_desc.get(m_name, "Evaluation metric")
        lines.append(f"| **`{m_name}`** | **{avg:.2f}** | 0.85+ | {desc} |")

    lines += [
        "",
        "---",
        "",
        "## 4. Detailed Per-Scenario Results",
        "",
        "| Scenario ID | Category | Title | Final Tool | Structural | Metrics | Status |",
        "|---|---|---|---|:---:|:---:|:---:|",
    ]

    for r in scenario_results:
        scn = r["scenario"]
        t = r.get("transcript", {})
        det_ok = all(v["passed"] for v in r["deterministic_checks"].values())
        met_ok = all(v["passed"] for v in r["metric_scores"].values())
        status_icon = "✅ PASS" if r["passed"] else "❌ FAIL"
        lines.append(
            f"| `{scn['id']}` | `{scn['category']}` | {scn['title'][:32]} | `{t.get('terminal_tool', 'none')}` | {'✅' if det_ok else '❌'} | {'✅' if met_ok else '❌'} | {status_icon} |"
        )

    lines += [
        "",
        "---",
        "",
        "## 5. Security & Isolation Verification",
        "",
        "1. **Zero ServiceNow Mutation Guarantee**: Live and recorded executions utilize `FakeWriteBackPort`. No modifications were posted to any remote ServiceNow PDI instance during this evaluation run.",
        "2. **Zero Credentials Committed**: All judge models and API keys are dynamically resolved from environment variables (`LITELLM_BASE_URL`, `LITELLM_API_KEY`, `OPENAI_API_KEY`).",
        "3. **Pipeline Gating Enforced**: The evaluation runner exits with `sys.exit(0)` on pass and `sys.exit(1)` on any threshold breach.",
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepEval Agent Behaviour & Safety Evaluation")
    parser.add_argument("--mode", choices=["recorded", "live"], default="recorded", help="Execution mode ('recorded' replay or 'live' run)")
    parser.add_argument("--config", default="eval/agent_config.yaml", help="Path to evaluation config YAML")
    parser.add_argument("--dataset", default=None, help="Optional override for scenario dataset JSON path")
    parser.add_argument("--report", default=None, help="Optional override for output report Markdown path")
    parser.add_argument("--llm-judge", action="store_true", help="Enable DeepEval G-Eval LLM-as-a-judge calls")

    args = parser.parse_args()
    code = run_evaluation(
        mode=args.mode,
        config_path=args.config,
        dataset_path=args.dataset,
        report_path=args.report,
        use_llm_judge=args.llm_judge,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
