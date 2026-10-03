## ServiceNow Write-back & Human Review

Sprint 3 (S3.6) adds the ServiceNow write-back client and human review surface for AI-generated incident suggestions.

### Python Write-back Client

Implementation:

`src/writeback/servicenow_writeback.py`

The `ServiceNowWritebackClient` provides:

* `add_work_note()`
* `suggest()`
* `escalate()`

All write-back operations use the ServiceNow Incident Table API.

The client uses an explicit allow-list of AI-managed fields:

* `x_2216229_sprint_1_ai_status`
* `x_2216229_sprint_1_ai_confidence`
* `x_2216229_sprint_1_ai_suggested_response`
* `x_2216229_sprint_1_human_review_required`
* `x_2216229_sprint_1_ai_processed`
* `work_notes`

`comments` is intentionally not part of the AI write-back allow-list.

Customer-facing communication is performed by the human fulfiller through the ServiceNow review UI.

### ServiceNow Field Mapping

The write-back client maps AI output to the following Incident fields:

| AI purpose               | ServiceNow field                           | Write behavior                                                                    |
| ------------------------ | ------------------------------------------ | --------------------------------------------------------------------------------- |
| AI status                | `x_2216229_sprint_1_ai_status`             | Written by `suggest()` and `escalate()`                                           |
| AI confidence            | `x_2216229_sprint_1_ai_confidence`         | Written by `suggest()` and `escalate()` (`0.0` when nothing matched)              |
| AI suggested response    | `x_2216229_sprint_1_ai_suggested_response` | Written by `suggest()`; read-only on the form                                     |
| Human review flag        | `x_2216229_sprint_1_human_review_required` | Set (checked) by `suggest()` **and** `escalate()`; cleared only by a human action |
| AI processed flag        | `x_2216229_sprint_1_ai_processed`          | Set by `suggest()` and `escalate()`                                               |
| Internal work notes      | `work_notes`                               | AI notes start with `[AI]`; escalations write `AI escalation reason: ...`         |
| Customer-facing comments | `comments`                                 | Not written directly by the AI client; populated through the human review actions |

The Python write-back client enforces an explicit field allow-list before every PATCH request. Any field outside the allow-list is rejected before an HTTP request is sent to ServiceNow.

Sensitive Incident fields such as `state`, `assigned_to`, `assignment_group`, `close_code`, and `close_notes` are intentionally excluded from the AI write-back allow-list.

### Atomic Write-back

`suggest()` and `escalate()` update the required AI fields and work notes through a single ServiceNow PATCH request.

`escalate()` sets AI Status to `escalated`, **keeps Human Review Required checked**, sets AI Processed, records the run's AI Confidence (`0.0` when nothing matched) and writes the reason as an internal work note.

Expected API failures are returned as:

```python
{"ok": False, "error": "..."}
```

instead of raising expected operational exceptions.

Transient HTTP failures use bounded retries for:

* `429`
* `500`
* `502`
* `503`
* `504`

The write-back client also validates the incident `sys_id` and request parameters before attempting the PATCH request.

### Human Review Surface

The ServiceNow Incident form provides three review actions:

1. **Approve AI Suggestion**

   * Available only when the AI status is `suggested` and human review is required.
   * Copies the AI suggestion into the customer-facing `comments` field, **without** the internal `Suggested resolution (pending human approval):` header line.
   * Clears `human_review_required`.
   * Saves the incident.

2. **Edit AI Suggestion**

   * Available under the same review conditions.
   * Copies the AI suggestion into `comments` (same header removal as Approve).
   * Allows the fulfiller to review and modify the customer-facing response before saving.

3. **Reject AI Suggestion**

   * Available when the AI status is `suggested` and human review is required.
   * Clears `human_review_required`.
   * Changes `ai_status` to `escalated`.
   * Adds an internal work note documenting the rejection.
   * Saves the incident.

### ServiceNow scripts in this repo

The PDI configuration is versioned in `servicenow/` (copy each file into the matching record in the PDI, and keep both identical):

| File                                                    | PDI record                                                                 |
| ------------------------------------------------------- | -------------------------------------------------------------------------- |
| `servicenow/business_rules/AI_Confidence_Validation.js` | Business rule: AI Confidence must be 0.0 to 1.0 (both ends allowed)        |
| `servicenow/business_rules/AI_Lifecycle_Guard.js`       | Business rule: clears Human Review when a **human** acts; ignores AI notes |
| `servicenow/ui_actions/AI_Approve.js`, `AI_Edit.js`, `AI_Reject.js` | UI actions on the Incident form                                |
| `servicenow/ui_policies/AI_Fields_Read_Only.js`         | UI policy: AI fields are read-only on the form                             |

The AI Lifecycle Guard treats a work note as written by the AI when it starts with `[AI]`, contains `AI escalation reason:`, or was written by the user named in the optional system property `x_2216229_sprint_1.ai_integration_user`. This matters because escalations keep Human Review checked: an AI note must never switch it off.

The logic of these scripts is tested without a PDI: `node --test tests/js/servicenow_scripts.test.js` (also run by `pytest`).

---

---

## 🤖 ReAct Agent Loop (Sprint 3 · S3.4)

The incident pipeline is driven by an autonomous **ReAct loop** (Thought → Action → Observation). The LLM decides when to search the knowledge base. It answers **only** from retrieved articles, and when nothing relevant exists it hands off to a human. Every rule that matters is **enforced in code**, not just asked for in the prompt.

### How a run works

```text
Webhook → Celery worker → IncidentContextPreparer (sanitize, is_safe)
         │  is_safe = False → rejected, agent never runs
         ▼
run_agent(sys_id, incident, tools, ctx)
   ┌─────────────────────────────────────────────────────────┐
   │ LLM (bind_tools) ── Thought + Action ──► tool call       │
   │        ▲                                   │             │
   │        └──────── Observation (JSON) ◄──────┘             │
   │ guardrails: budgets · search cap · repeated query ·      │
   │   grounding gate · LLM retry · stop on write-back error  │
   └─────────────── ends with suggestAnswer | requestHR ─────┘
         ▼
response_formatter (2nd citation check) → console trace → result payload (log only)
```

**Who writes to ServiceNow?** The agent's own tools (`addworknote`, `suggestAnswer`, `requestHR`) do, through the write-back port (`src/agent/factory.py` → `ServiceNowWritebackAdapter`). `process_incident()` sends nothing to ServiceNow; its `Pipeline result for ...` log line is only a log.

| File                                 | Role                                                                    |
| ------------------------------------ | ----------------------------------------------------------------------- |
| `src/agent/react_agent.py`           | The loop, guardrails, `AgentConfig`, `AgentResult`, `AgentFailure`      |
| `src/agent/prompts/system_prompt.py` | Versioned system prompt (`PROMPT_VERSION`, changelog; now `v1.3`)       |
| `src/agent/run_context.py`           | Per-run state: retrieved articles, scores, searches, outcome, event log |
| `agent/agent.py`                     | Task 5 retriever (`KnowledgeRetriever`) used by `searchKB`              |
| `run_pipeline.py`                    | `process_incident()`, called by the Celery worker                       |
| `tests/test_agent_loop.py`           | Offline agent-loop tests                                                |
| `scripts/try_agent.py`               | One real LLM run, printing the full transcript (fake write-back port)   |
| `scripts/make_evidence.py`           | Regenerates `docs/evidence/*.md` from real runs (fake write-back port)  |

### Entry point and result

```python
from src.agent.react_agent import run_agent

result = run_agent(sys_id, incident, tools, ctx=run_ctx)

result.status
result.terminal_tool
result.iterations
result.steps
```

`AgentResult` also carries `procedure`, `sources`, `reason`, `searches`, `grounding_rejections`, `fallback_reason`, `total_tokens`, `max_score`, `retrieved_chunks`, and `prompt_version`.

Unrecoverable LLM failures raise `AgentFailure`, which the pipeline turns into an escalation.

### Tools

| Tool                                | Terminal | Purpose                                                   |
| ----------------------------------- | -------- | --------------------------------------------------------- |
| `searchKB(query)`                   | No       | Dense search over published KB chunks                     |
| `addworknote(note)`                 | No       | Internal note (written to ServiceNow with an `[AI]` prefix) |
| `suggestAnswer(procedure, sources)` | Yes      | Submit a grounded, numbered, cited fix for human approval |
| `requestHR(reason)`                 | Yes      | Hand the incident to a human                              |

No tool can resolve, close, or reassign an incident. That boundary is structural.

### Citations

Every step of a suggested procedure ends with `[Article: <article_id>]`, where `<article_id>` is exactly what `searchKB` returned. Both ServiceNow KB numbers (`[Article: KB0010174]`) and PDF chunk documents (`[Article: doc_001]`) are valid. Citing an id that was not retrieved in the run is rejected.

### Guardrails

| Guardrail              | Rule                                                                                                   | When broken                                                         |
| ---------------------- | ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------- |
| Guaranteed termination | Max iterations (`AGENT_MAX_ITERATIONS`, 6), time budget (`AGENT_MAX_SECONDS`, **30**), token budget (`AGENT_MAX_TOKENS`, 20000) | Forced `requestHR`                                                  |
| Search cap             | Max `AGENT_MAX_SEARCHES` (3) `searchKB` calls; the same query twice is blocked                         | Error observation; the model must finish                            |
| Grounding gate         | `suggestAnswer` = numbered steps only, every step cited, only retrieved article ids cited              | Rejected with feedback; after `AGENT_MAX_GROUNDING_REJECTIONS` (2) the run becomes `requestHR` |
| Plain-text answer      | The model must end with a final tool                                                                   | One nudge (`AGENT_MAX_NUDGES`, 1), then forced `requestHR`          |
| LLM errors             | Transient errors retried with backoff (`AGENT_LLM_RETRIES` 2, `AGENT_RETRY_BASE_DELAY` 1 s)            | `AgentFailure`, the pipeline escalates                              |
| Write-back failure     | The **first** failed ServiceNow write (`addworknote`, `suggestAnswer`, `requestHR`) stops the run      | No retries, no forced `requestHR`; run closed locally as `escalated` (`fallback_reason` starts with `write-back failed`) |

The 30 s default for `AGENT_MAX_SECONDS` leaves a safe margin under the Celery worker's 60 s soft limit (`Worker/celery_app.py`).

### Configuration (`.env`, all optional)

`AGENT_MAX_ITERATIONS`, `AGENT_MAX_SECONDS`, `AGENT_MAX_TOKENS`, `AGENT_MAX_NUDGES`, `AGENT_MAX_SEARCHES`, `AGENT_MAX_GROUNDING_REJECTIONS`, `AGENT_LLM_RETRIES`, `AGENT_RETRY_BASE_DELAY`, `LLM_MODEL`, `LLM_TEMPERATURE`, `SCORE_THRESHOLD`, `TOP_K`. Invalid or non-positive values fall back to the defaults above.

### Manual runs and evidence

Both scripts use the in-memory `FakeWriteBackPort`, so they can never write to a real ServiceNow incident (they still call the real LLM and Qdrant):

```bash
python -m scripts.try_agent "wifi keeps disconnecting on my laptop"
python -m scripts.make_evidence      # rewrites docs/evidence/answerable_run.md, unanswerable_run.md, injection_run.md
```

### Tests

```bash
python -m pytest                     # Python tests (offline)
node --test tests/js/servicenow_scripts.test.js   # ServiceNow script logic (also run by pytest)
```

## RAG Evaluation (Sprint 4: Trust & Hardening)

A repeatable pipeline that measures how well the assistant **retrieves** knowledge-base articles and how good and grounded its **suggested answers** are. It uses [DeepEval](https://deepeval.com) (LLM-judged metrics) plus a deterministic, non-LLM Hit@3 metric.

Findings and recommendations from the first baseline run: [`docs/eval_findings.md`](docs/eval_findings.md). Terminal proof of that run: `docs/evidence/run_log.txt`.

### What is in `eval/`

| Path | Purpose |
|---|---|
| `datasets/rag_golden.json` | 43 incidents (36 answerable, 7 unanswerable; 9 Arabic or bilingual) with expected articles, expected answers and provenance |
| `datasets/kb_index.json` | The 25 real KB article numbers and titles, used to validate the dataset |
| `adapters.py` | `RagAdapter` interface: `retrieve(query, top_k)` and `generate_answer(...)`. `LiveAdapter` (real Qdrant + agent) and `SnapshotAdapter` (offline replay) |
| `record_snapshot.py` | Records live results into `fixtures/rag_snapshot.json` |
| `hit_at_k.py` | Deterministic Hit@k (no LLM) |
| `judge.py` | LLM judge for DeepEval, using the LiteLLM proxy from environment variables |
| `run_rag_eval.py` | The single evaluation command |
| `config.yaml` | Paths, `top_k`, and every threshold |
| `reports/` | `rag_report.md` and `rag_report.json` (generated) |

### Setup

Python 3.12 and [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Environment variables (in `.env`; **never commit real values**):

| Variable | Used for |
|---|---|
| `LITELLM_BASE_URL`, `LITELLM_API_KEY` | The judge (and the agent) connect to the LiteLLM proxy |
| `EVAL_JUDGE_MODEL` | Judge model name. Optional: falls back to `LLM_MODEL` |
| `LLM_MODEL` | Agent model (also the fallback judge model) |
| `QDRANT_URL`, `QDRANT_API_KEY` | Live mode only |
| `EMBEDDING_MODEL_NAME`, `SCORE_THRESHOLD`, `TOP_K` | Live mode; recorded in the snapshot metadata |

No keys or model names are stored in code, config or snapshots.

### Snapshot mode (default, offline)

Replays the recorded retrieval and agent results, so it needs no Qdrant, embedding model or agent. Only the judge LLM is called.

```bash
uv run python -m eval.run_rag_eval
```

Save a terminal log as evidence:

```bash
mkdir -p docs/evidence
uv run python -m eval.run_rag_eval 2>&1 | tee docs/evidence/run_log.txt
```

Useful options:

| Option | Effect |
|---|---|
| `--no-llm` | Deterministic metrics only (Hit@3, refusal, score separation). No judge calls |
| `--check-judge` | Sends one test prompt to the judge and exits |
| `--no-cache` | Ignore cached judge results (`reports/deepeval_cache.json`) |
| `--limit N` | First N cases only |
| `--strict` | Exit code 1 if any threshold fails (useful in CI) |

If a query is not found in the snapshot (for example after the dataset was edited), the run stops with an error asking you to re-record. It never falls back silently.

### Live mode

Runs the real stack: embeds each incident with the configured model, searches Qdrant, and runs the real ReAct agent. The agent uses `FakeWriteBackPort`, so **nothing is ever written to ServiceNow**.

```bash
uv run python -m eval.run_rag_eval --mode live
```

### Recording a new snapshot

Needs the live stack. The embedding model is cached in the Docker volume, so the simplest way (especially on Windows) is to record inside the app container:

```bash
docker compose run --rm --no-deps fastapi_app python -m eval.record_snapshot
```

Useful options: `--force` (re-record everything), `--limit 3` (smoke test), `--out PATH` (write elsewhere). Cases already recorded are reused. To test a different `SCORE_THRESHOLD` without editing `.env`:

```bash
docker compose run --rm --no-deps -e SCORE_THRESHOLD=0.55 fastapi_app python -m eval.record_snapshot --out eval/fixtures/rag_snapshot_t055.json
```

(then point `paths.snapshot` in `eval/config.yaml` to that file).

### Configuration (`eval/config.yaml`)

- `retrieval.top_k`: chunks retrieved per query. `hit_k`: k for Hit@k. `dedupe_docs`: count several chunks of one article once.
- `thresholds.*`: pass thresholds for every metric (see below).
- `judge.*`: **names** of the environment variables that hold the judge model, URL and key. `max_concurrency` limits parallel judge calls.

### Metrics

| Metric | Type | What it answers |
|---|---|---|
| Hit@3 | Deterministic | Is at least one expected article among the top 3 retrieved articles? (answerable cases only) |
| Contextual precision | DeepEval | Are the relevant chunks ranked above the irrelevant ones? |
| Contextual recall | DeepEval | Does the retrieved text contain everything the expected answer needs? |
| Contextual relevancy | DeepEval | How much of the retrieved text is actually on topic? |
| Faithfulness | DeepEval | Does the suggested answer say only what the retrieved chunks support? |
| Answer relevancy | DeepEval | Does the answer address the incident? |
| Procedure and citation | DeepEval G-Eval (custom) | Is the answer a numbered procedure with a `[Article: KBxxxxxxx]` citation per step? |
| Citation grounded | Deterministic | Does every cited article appear among the chunks the agent retrieved? |
| Refusal rate | Deterministic | Share of unanswerable incidents that were escalated instead of answered |

Retrieval metrics run on all answerable cases. Generation metrics run only on cases where the agent produced an answer.

### Reading the report (`eval/reports/rag_report.md`)

1. **Summary table:** each metric, its result, its threshold and PASS/FAIL. A DeepEval metric passes when its mean score reaches the threshold. A metric marked with errors means the judge failed on some cases; fix the connection and re-run (successful results are cached).
2. **False refusals:** answerable incidents the agent escalated instead of answering. A high number with a high Hit@3 means retrieval is fine but the answer/escalate decision is too strict.
3. **Score separation:** the best retrieval score for answerable versus unanswerable incidents. AUC is the chance that an answerable incident scores higher than an unanswerable one (1.0 is perfect separation, 0.5 is no separation). The sweep table shows, per threshold, how many answerable incidents would be kept and how many unanswerable ones rejected; the best balanced accuracy is marked. The second table uses the scores the **agent** saw, because it writes its own search queries.
4. **Flagged cases:** every case with a miss, a wrong escalation, a hallucinated answer, or a metric below its threshold, with the reasons.
5. **All cases:** expected versus retrieved articles, rank, best score and outcome.

`rag_report.json` holds the same data plus the judge's written reason for each score.

### Tests

Offline, no LLM, no network:

```bash
uv run pytest tests/test_eval_dataset.py -q
```

They check the dataset schema (size, language mix, article IDs, numbered answers with citations, provenance, no copied titles) and the Hit@k logic.
