# barq-sprints-ai-servicenow-support-assistant-g5

An event-driven, RAG-powered ServiceNow assistant that retrieves trusted knowledge, drafts cited resolutions, and routes responses for human approval.

## Getting started

### 1. Install `uv`

Dependencies are managed via `uv` and `pyproject.toml`.

**macOS / Linux**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell)**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Verify the installation:

```bash
uv --version
```

### 2. Install dependencies

From the project root:

```bash
uv sync
```

This creates the `.venv` and installs the project dependencies.

If dependencies are changed:

```bash
uv add <package>

uv lock

uv export --no-hashes --emit-index-url --format requirements-txt -o requirements.txt
```

Commit the updated dependency files:

```text
pyproject.toml
uv.lock
requirements.txt
```

#### Updating dependencies

`pyproject.toml` is the source of truth. `requirements.txt` is generated from it — never edit it by hand.

After adding, removing, or changing a package:

```bash
uv add <package>          # or edit pyproject.toml, then: uv lock
uv export --no-hashes --emit-index-url --format requirements-txt -o requirements.txt
```

Commit all three files together: `pyproject.toml`, `uv.lock`, `requirements.txt`.

### 3. Set up your environment file

Copy the example environment file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Fill in the required environment variables.

### 4. Required environment variables

#### ServiceNow

| Variable                    | Description                                      |
| --------------------------- | ------------------------------------------------ |
| `SERVICENOW_INSTANCE_URL`   | ServiceNow PDI base URL without a trailing slash |
| `SERVICENOW_USERNAME`       | Dedicated ServiceNow integration user            |
| `SERVICENOW_PASSWORD`       | Integration user's password                      |
| `SERVICENOW_KB_ID`          | Knowledge Base Sys ID                            |
| `SERVICENOW_KB_CATEGORY_ID` | Knowledge Base Category Sys ID                   |

#### Webhook and worker

| Variable           | Description                                           |
| ------------------ | ----------------------------------------------------- |
| `WEBHOOK_SECRET`   | Secret used to verify ServiceNow webhook signatures   |
| `REDIS_URL`        | Redis URL used by Celery as broker and result backend |
| `INCIDENT_HANDLER` | Dotted Python path for the incident handler           |

Example:

```text
REDIS_URL=redis://redis:6379/0
INCIDENT_HANDLER=Worker.incident_handler.handle_incident
```

Set a unique `WEBHOOK_SECRET` and configure the same secret in ServiceNow.

Webhook requests must contain a valid `X-ServiceNow-Signature`.

### 5. Redis and PostgreSQL

Sprint 3 uses Redis as the Celery message broker and result backend.

PostgreSQL stores application events, completion markers, and dead-lettered events.

The Docker Compose setup provides:

```text
PostgreSQL
Redis
FastAPI
Celery Worker
```

## Running the application

### Run PostgreSQL only

For local FastAPI development:

```bash
docker compose up -d postgres_db
```

Then:

```bash
uv run uvicorn main:app --reload
```

FastAPI connects to PostgreSQL through:

```text
localhost:5433
```

### Run the complete application

Start all services:

```bash
docker compose up --build
```

This starts:

```text
FastAPI
PostgreSQL
Redis
Celery Worker
```

The Celery worker runs with bounded concurrency:

```text
--concurrency=2
```

Redis and PostgreSQL health checks are used before dependent services start.

### Run the Celery worker directly

The worker can also be started directly with:

```bash
celery -A Worker.celery_app:celery_app worker --loglevel=INFO --concurrency=2
```

## Sprint 3.5 — Celery Worker

The webhook endpoint performs the synchronous work required for request handling:

```text
Webhook
   |
   +--> Signature verification
   |
   +--> Event deduplication
   |
   +--> Queue Celery task
   |
   +--> HTTP 202 response
```

The actual incident processing runs asynchronously in the Celery worker:

```text
Celery Worker
   |
   +--> Validate worker payload
   |
   +--> Check completion marker
   |
   +--> Fetch incident from ServiceNow
   |
   +--> Prepare incident context
   |
   +--> Execute incident handler
   |
   +--> Mark event completed
```

### Celery reliability configuration

The worker uses:

```text
task_acks_late = True

task_reject_on_worker_lost = True

worker_prefetch_multiplier = 1

task_soft_time_limit = 60 seconds

task_time_limit = 90 seconds

Redis visibility_timeout = 120 seconds
```

The Redis visibility timeout is greater than the hard task time limit so an active task is not redelivered prematurely.

### Worker payload

The Celery task receives only the required event metadata:

```json
{
  "event_id": "string",
  "sys_id": "string",
  "number": "string",
  "received_at": "ISO timestamp"
}
```

The worker then retrieves the current incident directly from ServiceNow using the configured credentials.

## Retry policy

Transient failures are retried with bounded exponential backoff and jitter.

Retryable conditions include:

* Network timeouts
* Network/request errors
* HTTP `429`
* HTTP `5xx`
* `RetryableError`

The worker allows a maximum of **3 total attempts**:

```text
Attempt 1
   |
   +--> transient failure
          |
          v
       retry + backoff
          |
Attempt 2
   |
   +--> transient failure
          |
          v
       retry + backoff
          |
Attempt 3
   |
   +--> success
   |
   +--> failure → DLQ
```

Permanent failures are not retried.

These include:

* HTTP `4xx` except `429`
* `PermanentError`

## Dead-Letter Queue

When an event cannot be processed after the allowed attempts, it is persisted in PostgreSQL.

The DLQ stores:

```text
event_id
payload
error
attempts
created_at
updated_at
```

The dead-letter hook records the failure and produces structured logs containing:

```text
event_id
sys_id
attempt
outcome
```

Sensitive credentials and incident descriptions are not written to the worker's structured logs.

## DLQ CLI

The DLQ CLI is located at:

```text
Scripts/dlq.py
```

### Inspect DLQ

Run:

```bash
docker compose exec fastapi_app python Scripts/dlq.py inspect
```

This displays the currently stored dead-letter events, including their event ID, incident identifiers, attempt count, error, and timestamps.

### Requeue an event

Run:

```bash
docker compose exec fastapi_app python Scripts/dlq.py requeue <event_id>
```

The event is submitted back to Celery for processing.

After successful requeue, the corresponding DLQ record is removed.

## Event completion and idempotency

Ingress deduplication and task completion are handled independently.

The event log prevents duplicate webhook ingestion.

The completion marker prevents a redelivered Celery task from executing the incident-processing pipeline again after the event has already completed.

This allows late-acknowledged tasks to be safely redelivered after worker failures.

## Incident handler

Incident processing is pluggable through the `INCIDENT_HANDLER` environment variable.

Example:

```text
INCIDENT_HANDLER=Worker.incident_handler.handle_incident
```

The default handler delegates to the existing incident-processing pipeline.

## Evidence

Sprint 3.5 runtime evidence covers:

* Successful asynchronous task execution
* Retry with exponential backoff
* Retry exhaustion resulting in DLQ
* DLQ persistence in PostgreSQL
* DLQ requeue
* Worker crash followed by Celery task redelivery

Evidence screenshots are stored under:

```text
docs/evidence/
```

## Project structure

Relevant Sprint 3.5 files:

```text
Worker/
├── celery_app.py
├── tasks.py
├── dead_letter.py
├── errors.py
└── incident_handler.py

Scripts/
└── dlq.py

tests/
└── test_worker.py

docs/
└── evidence/

docker-compose.yml
README.md
```

## Running tests

Run the worker test suite with:

```bash
pytest -q tests/test_worker.py
```

Run the complete test suite with:

```bash
pytest -q
```


## 📄 PDF Parser CLI & Multimodal Ingestion Pipeline

The project includes an end-to-end PDF parsing and multimodal extraction script located in [`scripts/parse_pdf.py`](scripts/parse_pdf.py). It converts complex technical runbooks into structured Markdown with embedded Vision LLM extractions.

### 🛠️ Execution Commands

Run the parser CLI on any input PDF document:

```bash
# Parse a PDF and output results to data/parsed/doc_001
uv run scripts/parse_pdf.py --pdf kbpdf.pdf --output data/parsed/doc_001

# Force re-execution and overwrite existing outputs
uv run scripts/parse_pdf.py --pdf kbpdf.pdf --output data/parsed/doc_001 --overwrite
```

### 🎯 Parser Tool Selection Rationale
1. **IBM Docling (`docling`):** Selected for state-of-the-art layout analysis, native Markdown table export, bounding box tracking, and page division.
2. **RapidOCR (`rapidocr`):** Lightweight, multi-lingual OCR engine supporting Arabic & English text detection without heavy external dependencies.
3. **LiteLLM Vision Integration (`litellm`):** Converts complex sequence diagrams, flowcharts, and architecture diagrams into structured Markdown blockquotes.
4. **Parallel Processing (`ThreadPoolExecutor`):** Processes image extractions concurrently to achieve 5x faster processing.

### 📦 Contract Deliverables & Outputs
* **`document.md`**: Clean, standardized Markdown output containing consecutive `<!-- page: N -->` markers and injected image extractions.
* **`manifest.json`**: Complete metadata tracking image bounding boxes (`bbox`), page numbers, and processing status (`completed`).
* **`images/`**: Saved PNG picture items extracted from the PDF.

### 🧪 Running Contract Tests

Validate parser compliance against contract specifications:

```bash
uv run pytest tests/test_parser_contract.py
```

### ⚠️ Runtime Expectations & Known Constraints
* **GPU vs CPU Fallback:** Automatically utilizes PyTorch GPU acceleration when available, falling back seamlessly to CPU execution.
* **API Rate Limits:** When running parallel image vision extraction on documents with >20 diagrams, ensure your `LITELLM_BASE_URL` endpoint supports concurrent calls.

---

## 🤖 ReAct Agent Loop (Sprint 3 · S3.4)

The incident pipeline is driven by an autonomous **ReAct loop** (Thought → Action → Observation). The LLM decides when to search the knowledge base. It answers **only** from retrieved articles, and when nothing relevant exists it hands off to a human. Every rule that matters is **enforced in code**, not just asked for in the prompt.

### How a run works

```text
Webhook → IncidentContextPreparer (sanitize, is_safe)
        │  is_safe = False → escalate, agent never runs
        ▼
run_agent(sys_id, incident, tools, ctx)
   ┌─────────────────────────────────────────────────────────┐
   │ LLM (bind_tools) ── Thought + Action ──► tool call       │
   │        ▲                                   │             │
   │        └──────── Observation (JSON) ◄──────┘             │
   │ guardrails: budgets · search cap · repeated query ·      │
   │             grounding gate · LLM retry                   │
   └─────────────── ends with suggestAnswer | requestHR ─────┘
        ▼
response_formatter (2nd citation check) → console trace → write-back payload
```

| File | Role |
|---|---|
| `src/agent/react_agent.py` | The loop, guardrails, `AgentConfig`, `AgentResult`, `AgentFailure` |
| `src/agent/prompts/system_prompt.py` | Versioned system prompt (`PROMPT_VERSION`, changelog) |
| `src/agent/run_context.py` | Per-run state: retrieved articles, scores, searches, outcome, event log |
| `src/agent/local_tools.py` | Temporary tool layer (see *Swapping in S3.3 tools*) |
| `agent/agent.py` | Task 5 retriever (`KnowledgeRetriever`) used by `searchKB` |
| `run_pipeline.py` | `process_incident()`, called by the webhook background task |
| `tests/test_agent_loop.py` | 32 offline tests (scripted fake LLM, fake retriever) |
| `scripts/try_agent.py` | One real run, printing the full transcript |
| `scripts/make_evidence.py` | Regenerates `docs/evidence/*.md` from real runs |

### Entry point and result

```python
from src.agent.react_agent import run_agent

result = run_agent(sys_id, incident, tools, ctx=run_ctx)   # incident = pre-fetched IncidentContext
result.status          # "suggested" | "escalated"
result.terminal_tool   # "suggestAnswer" | "requestHR"  (exactly one per run, always set)
result.iterations      # LLM turns used
result.steps           # ordered log: llm / tool / guardrail / fallback events
```

`AgentResult` also carries `procedure`, `sources`, `reason`, `searches`, `grounding_rejections`, `fallback_reason`, `total_tokens`, `max_score`, `retrieved_chunks` and `prompt_version`. Unrecoverable LLM failures raise `AgentFailure`, which the pipeline turns into an escalation.

### Tools (exactly four)

| Tool | Terminal | Purpose |
|---|---|---|
| `searchKB(query)` | no | Dense search over **published** KB chunks; returns `relevant`, `max_score`, `threshold`, `results` |
| `addworknote(note)` | no | Internal note |
| `suggestAnswer(procedure, sources)` | **yes** | Submit a grounded, numbered, cited fix for human approval |
| `requestHR(reason)` | **yes** | Hand the incident to a human |

No tool can resolve, close or reassign an incident. That boundary is structural, and a test asserts it.

### Guardrails

| Guardrail | Rule | When broken |
|---|---|---|
| Guaranteed termination | Max iterations, time budget, token budget; one nudge if the model answers in plain text | Forced `requestHR`, logged in `steps` as `forced: true`, with `fallback_reason` recorded. Every test asserts exactly one valid terminal tool |
| Search cap | Max `AGENT_MAX_SEARCHES` `searchKB` calls per run | Call blocked; model told to finish |
| Repeated query | Queries are normalized (case, punctuation, spaces); duplicates are blocked | Call blocked; Qdrant is not hit |
| Grounding gate | `suggestAnswer` requires: a search returned `relevant: true`; every step is numbered and cited; every cited ID was actually retrieved; `sources` is non-empty | Rejected with feedback; after `AGENT_MAX_GROUNDING_REJECTIONS` the run becomes `requestHR` |
| Untrusted input | Incident text goes only into the user message, wrapped in `<incident_data>` and declared untrusted. Any delimiter planted inside the text is stripped first, so it cannot "close" the block early. The prompt forbids role changes, prompt disclosure and ticket actions | Offline tests + a real injection run |
| LLM resilience | 408/409/429/5xx, timeouts and connection errors are retried with exponential backoff | `AgentFailure` → pipeline escalates "AI model is unavailable"; the service keeps running |

### Configuration (`.env`, all optional)

| Variable | Default | Meaning |
|---|---|---|
| `LLM_TEMPERATURE` | `0` | Low by default for repeatable runs |
| `AGENT_MAX_ITERATIONS` | `6` | LLM turns per run |
| `AGENT_MAX_SECONDS` | `45` | Wall-clock budget per run |
| `AGENT_MAX_TOKENS` | `20000` | Token budget per run |
| `AGENT_MAX_NUDGES` | `1` | Reminders when the model answers in plain text |
| `AGENT_MAX_SEARCHES` | `3` | `searchKB` calls per run |
| `AGENT_MAX_GROUNDING_REJECTIONS` | `2` | Rejected suggestions before escalation |
| `AGENT_LLM_RETRIES` | `2` | Extra attempts on transient LLM errors |
| `AGENT_RETRY_BASE_DELAY` | `1.0` | Backoff base in seconds (doubles each retry) |

Invalid values log a warning and fall back to the default. `SCORE_THRESHOLD` and `TOP_K` (retrieval) are shared with Task 5.

### Running it

```bash
# Offline tests (no LLM / Qdrant / token needed)
python -m pytest tests/test_agent_loop.py -v

# Save the test proof for the PR
python -m pytest tests/test_agent_loop.py -v | tee docs/evidence/test_results.txt

# One real run with the full ReAct transcript
python -m scripts.try_agent "wifi keeps disconnecting on my laptop"

# Full pipeline (trace + write-back payload + outputs/)
python run_pipeline.py "wifi keeps disconnecting on my laptop"

# Regenerate evidence from real runs
python -m scripts.make_evidence
```

### Evidence (`docs/evidence/`)

`test_results.txt` holds the offline test log. The transcripts below come from real runs (Gemini via the Sprints LiteLLM proxy + Qdrant Cloud).

| File | Outcome | Shows |
|---|---|---|
| `answerable_run.md` | suggested | search → relevant (0.86) → grounded, cited procedure |
| `unanswerable_run.md` | escalated | two different queries, both below 0.70 → `requestHR`, no invented fix |
| `injection_run.md` (extra) | suggested | injection ignored; only the technical symptom was searched; no prompt leak or ticket action |

> **Why "Thought" is empty in the transcripts:** Gemini's function calling returns the tool call without visible reasoning text. The reasoning is still auditable through the Action → Observation chain and the guardrail events.

### Output of a run

`process_incident()` keeps the Sprint 2 payload (`ai_suggested_response`, `ai_confidence`, `human_review_required: true`, `escalated`, `citations`) and adds an `agent` block:

```json
"agent": {
  "prompt_version": "v1.1",
  "outcome": "suggested",
  "terminal_tool": "suggestAnswer",
  "iterations": 2,
  "searches": 1,
  "grounding_rejections": 0,
  "fallback_reason": null,
  "total_tokens": 2844
}
```

`ai_confidence` is the best retrieval score seen during the run (0.0 if nothing was retrieved).

### Swapping in S3.3 tools

`src/agent/local_tools.py` is a stand-in with the **same four tool names** as the S3.3 tool layer. It records outcomes in `RunContext` but does not write back to ServiceNow. When `build_tools(context, kb_client, writeback)` is merged, replace one line in `run_pipeline.py`:

```python
tools = build_local_tools(run_ctx, get_knowledge_retriever())
# →
tools = build_tools(run_ctx, kb_client, writeback)
```

The loop, guardrails and tests do not change. The loop still applies its own grounding gate before `suggestAnswer` runs.

### Known limits

- Write-back to ServiceNow is not wired here; that is S3.6.
- Runs execute in FastAPI background tasks, not Celery; that is S3.5.
- The time budget is checked between LLM calls. A single slow call is bounded by the LLM client timeout (30 s in `Services/llm.py`).
- The grounding gate checks citations and retrieval, not semantic faithfulness of each sentence. Human review remains mandatory for every suggestion.

