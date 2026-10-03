# RAG Evaluation Findings (Sprint 4: Trust & Hardening)

Baseline run of 3 October 2026 against the system as deployed: `BAAI/bge-m3` embeddings, Qdrant collection `kb_baai_bge_m3` (25 published articles), production `SCORE_THRESHOLD=0.70`, `TOP_K=5`, agent and judge model `gemini/gemini-3.6-flash`. Full numbers: `eval/reports/rag_report.md` and `rag_report.json`. Terminal proof: `docs/evidence/run_log.txt`.

## 1. Summary

**Retrieval is strong. The answer/escalate decision is the problem.**

| Area | Result |
|---|---|
| Hit@3 (deterministic) | **36/36 = 1.00** (target 0.80). Correct article ranked first in 33/36 cases. English 29/29, Arabic/mixed 7/7 |
| Contextual precision / recall / relevancy | 0.923 / 0.949 / 0.642 |
| Answers actually produced for answerable incidents | **9/36 (25%)**. The agent escalated the other 27 even though the right article was retrieved |
| Unanswerable incidents escalated | 7/7, but only because the agent escalates almost everything |
| Faithfulness / answer relevancy / numbered-procedure-with-citations (n = 9 answers) | 1.00 / 0.972 / 1.00. Citations point only to retrieved articles in 9/9 |

The headline numbers pass every threshold, yet a user would receive an automatic answer for only one incident in four. Retrieval metrics alone would hide this, so the end-to-end answer rate must be tracked next to them.

## 2. What was evaluated

- **Dataset:** 43 incidents written from the content of the 25 KB articles (symptoms and context, not titles): 36 answerable, 7 unanswerable (out-of-scope or near-miss topics such as software licensing, payroll portal, badge access), 9 Arabic or bilingual. Every case records its source articles, source steps and how it was derived.
- **Pipeline:** retrieval is measured on the raw incident text (top 5 chunks); the answer comes from the real ReAct agent running with a fake write-back port.
- **Method note:** the first judged run gave contextual recall 0.921 and scored case rag_005 at 0.00 although the right chunk was retrieved. The judge counted the `[Article: KB...]` tags in the expected answer as unsupported by the KB text. The tags are now removed before scoring recall (citations are checked by the G-Eval metric and a deterministic check). After the fix, recall is 0.949 and rag_005 scores 1.00.

## 3. Failing and flagged cases

### 3.1 Over-refusal (27 cases)

Every case the agent answered had a best agent-side score of 0.70 or higher (0.70 to 0.75). Every case it escalated scored below 0.70 (0.507 to 0.69). The 0.70 threshold alone explains all 27 refusals. `bge-m3` produces lower similarity scores than the `bge-base-en-v1.5` model the threshold was tuned for. The answer rate is 5/29 for English and 4/7 for Arabic/mixed (small numbers, but there is no sign of an Arabic penalty).

Examples of correct retrieval followed by refusal: rag_014, rag_015, rag_021 and rag_026 all had the expected article ranked first and were still escalated (rag_026: agent score 0.64).

### 3.2 Ranking errors (3 cases, article ranked 2nd)

| Case | Expected | Ranked first | Likely cause |
|---|---|---|---|
| rag_009 (clicked a fake "mailbox full" email, typed password) | KB0010158 Phishing | KB0010168 Forgotten Password | Shared vocabulary ("password"). Contextual precision 0.33 |
| rag_010 (trojan warning after installing a PDF converter) | KB0010159 Malware | KB0010156 Slow Computer | The incident also says the PC is slow. Precision 0.37 |
| rag_020 (flash drive missing in Explorer) | KB0010173 USB | KB0010152 External Monitor | Both are "device not detected" problems. Precision 0.64 |

These still count as Hit@3 hits, but the wrong article sits above the right one in the context passed to the agent.

### 3.3 Weak context (rag_016)

"Excel keeps closing after adding a PDF add-in" got contextual recall 0.50 and relevancy 0.17. All five scores were about 0.50 and three of the five chunks were unrelated (pop-ups, file recovery). The incident is specific (Excel, add-in) while the article is generic ("Application Crashes"), and the first two steps of that article were in chunks that were not retrieved.

### 3.4 Chunk duplication (affects many cases)

The five retrieved chunks cover on average only **2.6 distinct articles**. In 22 of 43 cases they come from two articles or fewer, and in 27 of 43 one article fills three or more of the five slots. Each article has only 3 to 9 short steps, so splitting them into small chunks mostly adds duplicates and splits procedures across chunks.

### 3.5 Unanswerable cases

All 7 were escalated, so the refusal rate is 1.00. This is not evidence of good judgement, because the same agent also refused 75% of answerable incidents. Near-miss cases scored highest on raw text: rag_041 (AutoCAD licence request, Arabic) 0.62 and rag_038 (Adobe licence) 0.59, both matching the software-installation article KB0010163.

## 4. Score separation between answerable and unanswerable incidents

Two views of the best retrieval score:

| | Answerable (n = 36) | Unanswerable (n = 7) | AUC |
|---|---|---|---|
| Raw incident text | mean 0.630, range 0.487 to 0.745 | mean 0.527, range 0.392 to 0.624 | 0.841 |
| Scores the agent saw (its own search queries) | mean 0.638, range 0.507 to 0.750 | mean 0.463, range 0.397 to 0.512 | **0.992** |

On raw text the two groups overlap heavily (0.49 to 0.62). The agent's own queries separate them much better: for five of the seven unanswerable cases the agent-side score is lower than the raw score (for example rag_038 0.59 to 0.47, rag_041 0.62 to 0.51), because the agent searches for the specific unsupported request ("Adobe licence") instead of the whole incident text. Overlap on the agent side is tiny: the highest unanswerable score is 0.512, and only one answerable case scores below it (rag_016 at 0.507); rag_010 (0.515) sits just above.

## 5. Threshold validation

### 5.1 Production score threshold (agent-side scores)

| Threshold | Answerable answered | Unanswerable rejected |
|---|---|---|
| 0.50 | 36/36 | 5/7 |
| 0.52 | 34/36 | 7/7 |
| **0.55** | **31/36** | **7/7** |
| 0.60 | 27/36 | 7/7 |
| 0.65 | 14/36 | 7/7 |
| **0.70 (current)** | **9/36** | 7/7 |

**Recommendation: set `SCORE_THRESHOLD=0.55`.** It raises the answer rate from 25% to 86% on this set while still rejecting every unanswerable case, and it keeps a margin of about 0.04 above the highest unanswerable score. The tightest threshold that rejects all 7 is 0.52, but the margin is only 0.008, which is too fragile.

Caveats: the threshold was chosen on the same 43 cases, and only 7 are unanswerable. It must be confirmed on a held-out set before it is treated as final. The evidence that it works is a re-recorded snapshot at 0.55 (see section 7, item 1).

### 5.2 Evaluation thresholds (`eval/config.yaml`)

The thresholds were set before seeing results. Checking them against the data:

| Metric | Threshold | Observed (min / mean) | Verdict |
|---|---|---|---|
| Hit@3 | 0.80 | 1.00 | Kept. It is a ceiling on this small KB, so raise to 0.90 once the dataset has harder cases |
| Contextual precision | 0.60 | 0.33 / 0.923 | Kept. It flags exactly the real ranking problems (rag_009, rag_010) |
| Contextual recall | 0.60 | 0.50 / 0.949 | Kept. It flags rag_016, a genuine chunking gap |
| Contextual relevancy | 0.30 | 0.17 / 0.642 | Lenient: only rag_016 fails. Raise to 0.50 after chunks are grouped by article (section 6, item 2) |
| Faithfulness | 0.80 | 1.00 / 1.00 | Not yet validated. All 9 answers sit at the ceiling |
| Answer relevancy | 0.70 | 0.75 / 0.972 | Not yet validated (n = 9) |
| Numbered procedure and citations (G-Eval) | 0.70 | 1.00 / 1.00 | Not yet validated |
| Refusal rate | 0.80 | 1.00 | Valid only together with the answer rate (section 1) |

The generation metrics were computed on only 9 answers, all of them the agent's most confident ones, and the set contains no deliberately bad answers. They cannot yet show that the thresholds would catch a real failure. After the threshold change there will be about 31 answers, and a few negative controls (answers with invented steps or missing citations) should be added.

Judge variance: answer relevancy moved from 0.922 to 0.972 between two runs on identical inputs, so differences of about 0.05 on 9 cases are noise. Results are cached so a given report is reproducible, but a fresh judge run can differ slightly.

## 6. Architectural improvements (in priority order)

1. **Recalibrate `SCORE_THRESHOLD` to 0.55 and add a review band.** Answer at 0.55 or higher. Between 0.50 and 0.55 suggest an answer flagged "low confidence, needs review" instead of escalating (the best score is already carried as the confidence value). Below 0.50 escalate. Re-calibrate every time the embedding model changes, and store the calibration run with the model name.
2. **Retrieve whole articles, not small chunks.** Articles are short, so index each as one chunk (or return all chunks of the top articles). This removes the duplicate-slot problem (section 3.4), keeps procedures complete (rag_016 recall) and should raise contextual relevancy. It needs a re-index, so it should be re-validated with this pipeline.
3. **Add a cross-encoder reranker over the top 10 candidates** (the `bge-reranker-v2-m3` family matches `bge-m3`). It targets the three ranking confusions in 3.2, where a related-but-wrong article is placed first.
4. **Use hybrid retrieval (dense plus BM25 or the sparse output of `bge-m3`)** for incidents that mention specific products or error strings (rag_016) where meaning-only matching gives flat scores around 0.50.
5. **Keep the agent's query rewriting and apply the confidence threshold to the agent's scores, not to the raw incident text.** It improved separation from AUC 0.84 to 0.99 (section 4). Add an explicit in-scope check for requests such as licensing and access approvals that resemble installer or account articles.
6. **Evaluation hardening:**
   - add at least 30 unanswerable cases and a held-out split for choosing thresholds;
   - use a judge model different from the agent model to avoid self-preference;
   - add negative controls for faithfulness, relevancy and the citation check;
   - run `uv run python -m eval.run_rag_eval --strict` on snapshot data in CI for every change to the KB, prompt, model or thresholds, and re-record the snapshot when those change.

## 7. Limitations and next steps

- The dataset was written by the team from the articles, so it may be easier than real tickets. 25 short articles also make Hit@3 easy to saturate.
- Only 7 unanswerable cases and 9 generated answers limit every conclusion about thresholds and generation quality.
- Snapshot mode replays recorded behaviour, so it detects regressions only after a new snapshot is recorded when the system changes.
- Next steps:
  1. Re-record with the recommended threshold and compare answer rate, false refusals and generation metrics on the larger answer set:
     `docker compose run --rm --no-deps -e SCORE_THRESHOLD=0.55 fastapi_app python -m eval.record_snapshot --out eval/fixtures/rag_snapshot_t055.json`
  2. Prototype whole-article retrieval and the reranker, and compare with this baseline using the same command.
