# RAG Evaluation Report

- Generated: 2026-10-03T16:46:03+00:00
- Mode: **snapshot**
- Cases: 43 (36 answerable, 7 unanswerable)
- Dataset sha256: `650c644702e3`
- Embedding model: `BAAI/bge-m3` | Agent LLM: `gemini/gemini-3.6-flash` | Judge: `gemini/gemini-3.6-flash`
- Production score threshold: 0.7 | top_k: 5

## Summary

| Metric | Result | Threshold | Status |
|---|---|---|---|
| Hit@3 (deterministic) | 1.000 (36/36) | 0.8 | PASS |
| Refusal on unanswerable | 1.000 (7/7) | 0.8 | PASS |
| contextual_precision | 0.923 mean over 36 | 0.6 | PASS |
| contextual_recall | 0.949 mean over 36 | 0.6 | PASS |
| contextual_relevancy | 0.642 mean over 36 | 0.3 | PASS |
| faithfulness | 1.000 mean over 9 | 0.8 | PASS |
| answer_relevancy | 0.972 mean over 9 | 0.7 | PASS |
| procedure_citation | 1.000 mean over 9 | 0.7 | PASS |

False refusals (answerable but escalated): 27/36. Citations pointing only to retrieved articles: 9/9.

Hit@3 by language: english 29/29; arabic_or_mixed 7/7.

## Score separation (top retrieval score)

| Group | n | mean | median | min | max |
|---|---|---|---|---|---|
| answerable | 36 | 0.63 | 0.6317 | 0.4869 | 0.7447 |
| unanswerable | 7 | 0.5268 | 0.5439 | 0.3922 | 0.6238 |

AUC (probability an answerable incident outscores an unanswerable one): **0.841**. At the production threshold 0.7: 0.139 of answerable kept, 1.000 of unanswerable rejected.

| Threshold | Answerable kept | Unanswerable rejected | Balanced accuracy |
|---|---|---|---|
| 0.20 | 1.0 | 0.0 | 0.5 |
| 0.25 | 1.0 | 0.0 | 0.5 |
| 0.30 | 1.0 | 0.0 | 0.5 |
| 0.35 | 1.0 | 0.0 | 0.5 |
| 0.40 | 1.0 | 0.143 | 0.571 |
| 0.45 | 1.0 | 0.143 | 0.571 |
| 0.50 | 0.972 | 0.286 | 0.629 |
| 0.55 | 0.944 | 0.571 | 0.758 **<- best** |
| 0.60 | 0.611 | 0.857 | 0.734 |
| 0.65 | 0.417 | 1.0 | 0.708 |
| 0.70 | 0.139 | 1.0 | 0.569 |
| 0.75 | 0.0 | 1.0 | 0.5 |
| 0.80 | 0.0 | 1.0 | 0.5 |
| 0.85 | 0.0 | 1.0 | 0.5 |
| 0.90 | 0.0 | 1.0 | 0.5 |

### Same analysis on the scores the agent itself saw

The agent writes its own search queries, so the best score it saw (which decides answer vs escalate) differs from the raw-incident score above.

| Group | n | mean | median | min | max |
|---|---|---|---|---|---|
| answerable | 36 | 0.6381 | 0.6395 | 0.5069 | 0.7496 |
| unanswerable | 7 | 0.4632 | 0.4665 | 0.3967 | 0.5122 |

AUC: **0.992**. At 0.7: answerable kept 0.250, unanswerable rejected 1.000. Best threshold in the sweep: **0.55** (balanced accuracy 0.931; answerable kept 0.861, unanswerable rejected 1.0).

## Failing or flagged cases

| Case | Type | Lang | Problems |
|---|---|---|---|
| rag_002 | answerable | en | escalated instead of answering (best score 0.56) |
| rag_003 | answerable | en | escalated instead of answering (best score 0.61) |
| rag_004 | answerable | en | escalated instead of answering (best score 0.59) |
| rag_005 | answerable | en | escalated instead of answering (best score 0.59) |
| rag_008 | answerable | en | escalated instead of answering (best score 0.72) |
| rag_009 | answerable | en | contextual_precision=0.33 < 0.6 |
| rag_010 | answerable | en | escalated instead of answering (best score 0.58); contextual_precision=0.37 < 0.6 |
| rag_011 | answerable | en | escalated instead of answering (best score 0.63) |
| rag_012 | answerable | en | escalated instead of answering (best score 0.58) |
| rag_013 | answerable | en | escalated instead of answering (best score 0.63) |
| rag_014 | answerable | en | escalated instead of answering (best score 0.57) |
| rag_015 | answerable | en | escalated instead of answering (best score 0.69) |
| rag_016 | answerable | en | escalated instead of answering (best score 0.50); contextual_recall=0.50 < 0.6; contextual_relevancy=0.17 < 0.3 |
| rag_017 | answerable | en | escalated instead of answering (best score 0.73) |
| rag_018 | answerable | en | escalated instead of answering (best score 0.65) |
| rag_019 | answerable | en | escalated instead of answering (best score 0.65) |
| rag_020 | answerable | en | escalated instead of answering (best score 0.49) |
| rag_021 | answerable | en | escalated instead of answering (best score 0.68) |
| rag_022 | answerable | en | escalated instead of answering (best score 0.56) |
| rag_023 | answerable | en | escalated instead of answering (best score 0.65) |
| rag_024 | answerable | en | escalated instead of answering (best score 0.60) |
| rag_025 | answerable | en | escalated instead of answering (best score 0.58) |
| rag_026 | answerable | en | escalated instead of answering (best score 0.56) |
| rag_027 | answerable | en | escalated instead of answering (best score 0.68) |
| rag_028 | answerable | en | escalated instead of answering (best score 0.68) |
| rag_031 | answerable | ar | escalated instead of answering (best score 0.65) |
| rag_034 | answerable | ar | escalated instead of answering (best score 0.60) |
| rag_035 | answerable | mixed | escalated instead of answering (best score 0.61) |

## All cases

| Case | Type | Lang | Expected | Top-3 articles | Rank | Best score | Outcome |
|---|---|---|---|---|---|---|---|
| rag_001 | answerable | en | KB0010174 | KB0010174, KB0010171 | 1 | 0.68 | suggested |
| rag_002 | answerable | en | KB0010171 | KB0010171, KB0010174, KB0010156 | 1 | 0.56 | escalated |
| rag_003 | answerable | en | KB0010172 | KB0010172, KB0010165, KB0010171 | 1 | 0.61 | escalated |
| rag_004 | answerable | en | KB0010155 | KB0010155, KB0010174 | 1 | 0.59 | escalated |
| rag_005 | answerable | en | KB0010155 | KB0010155, KB0010165 | 1 | 0.59 | escalated |
| rag_006 | answerable | en | KB0010168 | KB0010168, KB0010153 | 1 | 0.73 | suggested |
| rag_007 | answerable | en | KB0010153 | KB0010153, KB0010168, KB0010162 | 1 | 0.68 | suggested |
| rag_008 | answerable | en | KB0010162 | KB0010162, KB0010158, KB0010153 | 1 | 0.72 | escalated |
| rag_009 | answerable | en | KB0010158 | KB0010168, KB0010158, KB0010153 | 2 | 0.65 | suggested |
| rag_010 | answerable | en | KB0010159 | KB0010156, KB0010159 | 2 | 0.58 | escalated |
| rag_011 | answerable | en | KB0010167 | KB0010167, KB0010158, KB0010161 | 1 | 0.63 | escalated |
| rag_012 | answerable | en | KB0010156 | KB0010156 | 1 | 0.58 | escalated |
| rag_013 | answerable | en | KB0010151 | KB0010151, KB0010161, KB0010166 | 1 | 0.63 | escalated |
| rag_014 | answerable | en | KB0010166 | KB0010166, KB0010170, KB0010164 | 1 | 0.57 | escalated |
| rag_015 | answerable | en | KB0010164 | KB0010164, KB0010150, KB0010166 | 1 | 0.69 | escalated |
| rag_016 | answerable | en | KB0010150 | KB0010150, KB0010167, KB0010154 | 1 | 0.50 | escalated |
| rag_017 | answerable | en | KB0010163 | KB0010163, KB0010157 | 1 | 0.73 | escalated |
| rag_018 | answerable | en | KB0010157 | KB0010157, KB0010161, KB0010156 | 1 | 0.65 | escalated |
| rag_019 | answerable | en | KB0010152 | KB0010152, KB0010170, KB0010166 | 1 | 0.65 | escalated |
| rag_020 | answerable | en | KB0010173 | KB0010152, KB0010173 | 2 | 0.49 | escalated |
| rag_021 | answerable | en | KB0010170 | KB0010170 | 1 | 0.68 | escalated |
| rag_022 | answerable | en | KB0010169, KB0010161 | KB0010169, KB0010165, KB0010161 | 1 | 0.56 | escalated |
| rag_023 | answerable | en | KB0010161 | KB0010161, KB0010169 | 1 | 0.65 | escalated |
| rag_024 | answerable | en | KB0010165 | KB0010165, KB0010173 | 1 | 0.60 | escalated |
| rag_025 | answerable | en | KB0010154 | KB0010154, KB0010160 | 1 | 0.58 | escalated |
| rag_026 | answerable | en | KB0010160 | KB0010160, KB0010150, KB0010162 | 1 | 0.56 | escalated |
| rag_027 | answerable | en | KB0010165, KB0010172 | KB0010172, KB0010165 | 1 | 0.68 | escalated |
| rag_028 | answerable | en | KB0010174, KB0010171 | KB0010174, KB0010171 | 1 | 0.68 | escalated |
| rag_029 | answerable | en | KB0010155 | KB0010155, KB0010166, KB0010170 | 1 | 0.57 | suggested |
| rag_030 | answerable | ar | KB0010174 | KB0010174, KB0010171, KB0010170 | 1 | 0.59 | suggested |
| rag_031 | answerable | ar | KB0010155 | KB0010155, KB0010170 | 1 | 0.65 | escalated |
| rag_032 | answerable | ar | KB0010168 | KB0010168, KB0010153 | 1 | 0.70 | suggested |
| rag_033 | answerable | mixed | KB0010172 | KB0010172, KB0010171 | 1 | 0.72 | suggested |
| rag_034 | answerable | ar | KB0010151 | KB0010151, KB0010166, KB0010170 | 1 | 0.60 | escalated |
| rag_035 | answerable | mixed | KB0010169, KB0010161 | KB0010169, KB0010161, KB0010170 | 1 | 0.61 | escalated |
| rag_036 | answerable | ar | KB0010162 | KB0010162, KB0010153, KB0010158 | 1 | 0.74 | suggested |
| rag_037 | unanswerable | en | - | KB0010168, KB0010158, KB0010157 | - | 0.46 | escalated |
| rag_038 | unanswerable | en | - | KB0010163, KB0010155 | - | 0.59 | escalated |
| rag_039 | unanswerable | en | - | KB0010160, KB0010165, KB0010154 | - | 0.50 | escalated |
| rag_040 | unanswerable | en | - | KB0010165, KB0010168 | - | 0.54 | escalated |
| rag_041 | unanswerable | ar | - | KB0010163 | - | 0.62 | escalated |
| rag_042 | unanswerable | mixed | - | KB0010168, KB0010153 | - | 0.57 | escalated |
| rag_043 | unanswerable | en | - | KB0010158, KB0010168 | - | 0.39 | escalated |
