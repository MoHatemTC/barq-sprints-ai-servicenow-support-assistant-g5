# Evaluation Findings

This sprint focused on proving the retrieval stack and answer generation are grounded in the same KB corpus used by the application.

## Current status

The repository now contains an evaluation dataset and runner that can be executed locally to assess retrieval and answer quality. The evaluation pipeline is intentionally adapter-based so the same scoring logic can run either against live Qdrant content or an offline snapshot fixture.

## Dataset provenance

The golden dataset under `eval/datasets/rag_golden.json` is derived from the patterns in the published ServiceNow KB articles already indexed in the project. Each row is grounded in a troubleshooting pattern that is mapped to a likely KB article family rather than copied verbatim from an article title. The provenance field explains the relation to the source article family and the reason the case is answerable or deliberately unanswerable.

## Expected score separation

The evaluation design separates `answerable` and `unanswerable` incidents explicitly. In a healthy run, answerable incidents should cluster around higher retrieval hit rates and higher answer-grounding scores. Unanswerable incidents should be rejected or return a proper human-escalation answer without claiming a grounded fix.

## Threshold check

The default thresholds in `eval/config.yaml` are intentionally conservative:

- retrieval precision >= 0.75
- recall >= 0.60
- answer relevancy >= 0.70
- faithfulness >= 0.75
- G-Eval >= 0.80
- Hit@3 target >= 0.80

These thresholds help distinguish between a retrieval result that is merely plausible and a result that is grounded and usable for an end user.

## Recommended improvements

1. Replace the snapshot-only fallback with a stricter adapter that includes explicit article provenance metadata and richer document-section grounding.
2. Expand the dataset with more multilingual edge cases and long-tail troubleshooting incidents.
3. Add more explicit answerability rules for cases where the user description is too vague or outside the KB.
4. Add DeepEval integration once the dependency is approved and pinned in the project environment.
5. Capture a sample terminal run under `docs/evidence/` to provide proof of execution for PR review.

## Expected outcome

The sprint goal is to produce a consistent retrieval baseline, identify blind spots, and prevent the agent from answering from weak or missing evidence. The dataset and evaluation code give us a repeatable way to measure that quality over time.
