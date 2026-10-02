# Verification Record

## 1. Purpose

This document records the verification performed for the **AI ServiceNow Support Assistant**.

The purpose of the verification is to confirm that the documented system setup, runtime behavior, reliability mechanisms, ServiceNow integration, AI processing flow, and human-review workflow match the implemented project.

The verification covers:

* Python environment and dependency setup
* Docker Compose services
* FastAPI
* Redis
* Celery worker
* PostgreSQL event state
* Qdrant knowledge-base retrieval
* ServiceNow integration
* webhook authentication and validation
* asynchronous incident processing
* guardrails
* ReAct agent execution
* grounding validation
* ServiceNow write-back
* human review
* retry and dead-letter handling
* worker reliability
* automated tests

Verification evidence is stored under:

```text
docs/evidence/
```

No credentials, API keys, tokens, passwords, or other secrets are included in the verification evidence.

---

# 2. Verification Environment

The system was verified using:

```text
Python / uv
FastAPI
Celery
Redis
PostgreSQL
Qdrant
ServiceNow PDI
Docker Compose
```

The main local application services are:

```text
FastAPI
Celery Worker
PostgreSQL
Redis
```

Qdrant is configured through the project environment and is not currently defined as a Docker Compose service.

The verification was performed against the project repository and the configured ServiceNow PDI instance.

---

# 3. Repository and Python Environment

## 3.1 Repository Structure

Relevant project components include:

```text
App/
Routes/
Schemas/
Services/
Clients/
Worker/
agent/
src/
servicenow/
Scripts/
tests/
docs/
main.py
run_pipeline.py
reindex.py
Dockerfile
docker-compose.yml
pyproject.toml
uv.lock
.env.example
```

---

## 3.2 Dependency Installation

The project uses `uv` for Python environment and dependency management.

The project environment was initialized using:

```bash
uv sync
```

The installed Python runtime was checked using:

```bash
uv run python --version
```

Project commands were executed using the configured environment.

### Verification Result

The project dependencies were installed from the repository configuration and the Python environment was available for application, worker, and test execution.

---

# 4. Environment Configuration

The repository provides a sanitized environment template:

```text
.env.example
```

A local `.env` file was created from the template.

### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

### Linux / macOS

```bash
cp .env.example .env
```

The local configuration contains the required values for:

* ServiceNow
* PostgreSQL
* Redis
* Qdrant
* webhook authentication
* API authentication
* LLM / LiteLLM
* agent configuration

Actual credentials remain outside the repository.

The committed `.env.example` uses placeholders rather than real credentials.

---

# 5. FastAPI Verification

The FastAPI application was verified using the project application entry point.

The working local startup command is:

```bash
python -m uvicorn main:app --reload
```

FastAPI is responsible for:

```text
Receiving ServiceNow webhooks
Validating webhook requests
Persisting event state
Applying request guardrails
Queuing background processing
Exposing application endpoints
```

The AI processing pipeline is not executed synchronously inside the webhook request.

### Verification Result

The FastAPI application started successfully and exposed the configured application routes.

---

# 6. Docker Compose Verification

The local infrastructure can be started with:

```bash
docker compose up -d
```

Running containers can be inspected with:

```bash
docker compose ps
```

The expected local services are:

```text
FastAPI
Celery Worker
PostgreSQL
Redis
```

The local PostgreSQL configuration uses:

```text
Host:      5433
Container: 5432
```

Redis uses:

```text
6379
```

### Verification Result

The application infrastructure was brought up through the Docker Compose environment.

Evidence:

```text
docs/evidence/celery_fastapi.png
docs/evidence/Health check.png
```

---

# 7. Redis and Celery Worker Verification

Redis is used as the broker/backend for the Celery worker.

The worker can be started with:

```bash
celery -A Worker.celery_app:celery_app worker --loglevel=INFO --concurrency=2
```

The worker reliability configuration includes:

```text
task_acks_late = True
task_reject_on_worker_lost = True
worker_prefetch_multiplier = 1
```

The worker also uses bounded execution time and a Redis visibility timeout greater than the configured hard task limit.

The worker requires the configured incident handler:

```text
INCIDENT_HANDLER
```

### Verification Result

The Celery worker was started and verified as part of the asynchronous processing environment.

Evidence:

```text
docs/evidence/Celery_worker.png
docs/evidence/celery_fastapi.png
```

---

# 8. PostgreSQL Event State and Idempotency

PostgreSQL stores processing state for incident events.

The application uses:

```text
events_log
completed_events
dead_letter_events
```

These tables support:

* event persistence
* duplicate-event detection
* completion tracking
* dead-letter handling

The incident `sys_id` is used as the event idempotency key.

Expected duplicate-event behavior:

```text
First event
    ↓
accepted
    ↓
queued

Same sys_id received again
    ↓
duplicate detected
    ↓
duplicate_ignored
```

This prevents the same incident event from being submitted for another processing execution through the webhook path.

### Verification Result

The event-state and duplicate handling mechanisms were inspected and tested as part of the reliability verification.

Evidence:

```text
docs/evidence/requeue_Event.png
docs/evidence/Success_one.png
```

---

# 9. Qdrant and Knowledge Base Verification

The AI assistant uses Qdrant for semantic knowledge-base retrieval.

The configured embedding model is:

```text
BAAI/bge-base-en-v1.5
```

The configured vector size is:

```text
768
```

The KB collection is:

```text
kb_baai_bge_base_en_v1_5
```

The retrieval flow is:

```text
Incident / Search Query
        ↓
BGE Embedding
        ↓
Qdrant
        ↓
Top-K KB Chunks
        ↓
Similarity Scores
```

Retrieval is restricted to published knowledge.

The configured similarity threshold is:

```text
0.70
```

The knowledge-base ingestion process retrieves published ServiceNow articles, cleans the content, chunks the text, creates embeddings, and upserts the resulting vectors into Qdrant.

---

## 9.1 Qdrant Setup Issues

During setup, Qdrant connectivity initially encountered configuration issues.

The first observed failure was:

```text
403
```

The Qdrant URL/environment configuration was corrected.

A subsequent request returned:

```text
404 Collection not found
```

This indicated that Qdrant was reachable but the expected collection was not available.

The knowledge-base indexing/reindexing process was then used to create and populate the expected collection.

### Verification Result

The Qdrant knowledge-base configuration and retrieval pipeline were brought into a working state.

---

# 10. ServiceNow Webhook Verification

The incident webhook endpoint is:

```text
POST /api/webhook
```

The webhook expects:

```text
X-ServiceNow-Signature
```

The signature is validated using HMAC-SHA256 and the configured webhook secret.

The incident payload contains:

```text
sys_id
number
short_description
description
```

The request processing flow is:

```text
ServiceNow
     ↓
POST /api/webhook
     ↓
HMAC verification
     ↓
Payload validation
     ↓
PostgreSQL event state
     ↓
Celery / Redis
     ↓
HTTP 202
```

---

## 10.1 Successful Webhook Processing

A valid webhook request returns:

```text
202 Accepted
```

The request is persisted and a minimal worker payload is queued.

The AI pipeline does not run inside the HTTP request.

---

## 10.2 Invalid Signature

A missing or invalid HMAC signature is rejected with:

```text
401 Unauthorized
```

The request does not enter the Celery processing path.

---

## 10.3 Invalid Payload

A request that does not satisfy the incident payload validation rules is rejected with:

```text
422 Unprocessable Entity
```

These status codes form part of the webhook contract.

---

# 11. Asynchronous Incident Processing

The webhook queues only the information required to identify the processing event.

The worker payload contains:

```text
event_id
sys_id
number
received_at
```

The complete incident description is not stored in the Celery payload.

The processing flow is:

```text
FastAPI
    ↓
Minimal Worker Payload
    ↓
Redis
    ↓
Celery Worker
    ↓
Fresh ServiceNow GET
    ↓
Guardrails
    ↓
ReAct Agent
    ↓
ServiceNow Write-back
```

FastAPI handles:

```text
Receive
Authenticate
Validate
Persist
Queue
```

The Celery worker handles:

```text
Retrieve
Process
Reason
Search KB
Write back
```

---

# 12. Fresh Incident Retrieval

After receiving the queued event, the worker retrieves the current incident directly from ServiceNow.

The flow is:

```text
Celery Worker
      ↓
ServiceNow GET
      ↓
Fresh Incident Data
      ↓
Guardrails
      ↓
ReAct Agent
```

This ensures that the AI pipeline works from the current ServiceNow incident rather than relying on potentially stale incident text stored in the queue.

---

# 13. Guardrail Verification

Incident content received from ServiceNow is treated as untrusted external input.

The guardrail layer performs:

```text
Length limiting
Sensitive-value masking
Keyword/tag extraction
Prompt-injection detection
Untrusted-data wrapping
```

Guardrails are applied before the AI agent processes the incident.

The worker also applies guardrail processing after retrieving the fresh ServiceNow incident.

This second validation is intentional because the worker retrieves a new copy of the incident.

---

## 13.1 Unsafe Input

If an incident is detected as unsafe or containing a prompt-injection pattern, it is not passed directly into the normal AI processing flow.

The expected flow is:

```text
Incident
    ↓
Guardrails
    ↓
Unsafe input detected
    ↓
Rejected / Flagged
```

This prevents untrusted incident content from being treated as trusted agent instructions.

---

# 14. ReAct Agent Verification

The AI processing layer uses a custom ReAct loop.

The agent exposes exactly four tools:

```text
searchKB
addworknote
suggestAnswer
requestHR
```

The agent does not provide tools for:

```text
Resolving incidents
Closing incidents
Reassigning incidents
```

The agent is controlled by runtime limits including:

```text
Maximum iterations
Maximum execution time
Maximum token usage
Maximum KB searches
Maximum grounding rejections
LLM retry policy
```

The agent operates within bounded execution limits rather than running indefinitely.

---

# 15. Knowledge Retrieval and Grounding

The `searchKB` tool retrieves relevant published knowledge-base chunks from Qdrant.

The general flow is:

```text
Incident
    ↓
searchKB
    ↓
Qdrant
    ↓
Retrieved KB Chunks
    ↓
Agent Reasoning
    ↓
Grounding Validation
    ↓
Suggestion or Escalation
```

A suggestion must be grounded in retrieved KB content.

The grounding validation checks that:

* relevant KB content was retrieved
* the generated response contains a numbered procedure
* the procedure contains citations
* cited article IDs were actually retrieved
* valid sources are available

If grounding cannot be established, the agent does not simply invent a solution.

The agent can reject an insufficiently grounded answer and continue within its configured limits. If sufficient grounding cannot be achieved, the incident can be escalated through `requestHR`.

---

# 16. ServiceNow Write-back Verification

The ServiceNow write-back layer supports:

```text
suggest()
escalate()
add_work_note()
```

The client uses an explicit allow-list of AI-controlled fields.

The AI suggestion is written as internal processing data rather than being directly sent as customer-facing communication.

Transient ServiceNow failures such as:

```text
429
500
502
503
504
```

are retryable.

The client applies backoff between retries.

If write-back fails during processing, the pipeline stops additional write operations rather than continuing against an uncertain ServiceNow state.

Evidence:

```text
docs/evidence/12_live_suggest_terminal.png
docs/evidence/13_live_suggest_servicenow.png
docs/evidence/14_live_escalate.png
```

---

# 17. Human Review Verification

AI-generated suggestions require human review before customer-facing communication.

The intended lifecycle is:

```text
AI Suggestion
      ↓
Human Review
   ↙    ↓    ↘
Approve Edit Reject
```

The AI does not directly write its generated response to the customer-facing `comments` field.

Internal AI processing information uses:

```text
work_notes
```

Customer-facing communication is handled through:

```text
comments
```

after human review.

---

## 17.1 Review Actions

The ServiceNow interface provides:

```text
Approve
Edit
Reject
```

The verification evidence covers:

```text
UI Policy
UI Actions
Review action visibility
Approve result
Edit result
Reject result
```

Evidence:

```text
docs/evidence/01_ui_policy_record.png
docs/evidence/02_ui_policy_actions.png
docs/evidence/03_ui_actions_list.png
docs/evidence/04_review_actions_visible.png
docs/evidence/05_review_actions_hidden.png
docs/evidence/06_approve_result.png
docs/evidence/07_edit_result.png
docs/evidence/08_reject_result.png
```

---

# 18. Lifecycle Guard Verification

The ServiceNow lifecycle guard controls when AI review state can be cleared.

The verification covers:

```text
Human work note
Terminal incident state
```

Evidence:

```text
docs/evidence/09_lifecycle_guard_work_note.png
docs/evidence/10_lifecycle_guard_terminal.png
```

This verifies the distinction between AI-generated internal work notes and lifecycle actions that affect the review state.

---

# 19. Confidence Validation

The project validates the confidence value used during AI processing and write-back.

The verification includes the ServiceNow-side confidence validation behavior.

Evidence:

```text
docs/evidence/11_confidence_validation.png
```

The confidence value represents the system's retrieval/processing confidence and should not be interpreted as a calibrated probability of correctness.

---

# 20. Retry and Dead-Letter Verification

Retryable failures are handled through the configured Celery retry mechanism.

The general flow is:

```text
Processing
    ↓
Retryable Failure
    ↓
Retry
    ↓
Retryable Failure
    ↓
Retry Limit
    ↓
Dead Letter
```

Permanent failures are not retried indefinitely.

The project maintains dead-letter processing state through:

```text
dead_letter_events
```

The verification evidence covers:

```text
Retry behavior
Retry limit exceeded
Dead-letter inspection
Event requeue
```

Evidence:

```text
docs/evidence/Retry_exceed.png
docs/evidence/DLQ_inspections.png
docs/evidence/requeue_Event.png
```

---

# 21. Worker Reliability and Execution Limits

The Celery worker uses:

```text
task_acks_late = True
task_reject_on_worker_lost = True
worker_prefetch_multiplier = 1
```

These settings support task redelivery when a worker process is lost.

The intended behavior is:

```text
Task received
      ↓
Worker processing
      ↓
Worker lost
      ↓
Task eligible for redelivery
      ↓
New worker receives task
```

Completion state is checked so that an already completed event can be skipped if a task is redelivered.

Worker execution limits and runtime health were also verified.

Evidence:

```text
docs/evidence/Celery_worker.png
docs/evidence/time_limit_test.png
docs/evidence/Health check.png
```

---

# 22. Automated Test Verification

The project's automated tests were executed using:

```bash
pytest
```

The test evidence includes successful test execution and runtime checks.

Evidence:

```text
docs/evidence/15_python_tests_passed.png
docs/evidence/tests.png
```

The verification covers areas including:

```text
Webhook behavior
ServiceNow integration
Agent behavior
Write-back
Retry handling
Failure handling
Reliability controls
```

---

# 23. Verification Issues and Fixes

The following issues were encountered during setup and verification.

| Issue                                                                | Probable Cause                                         | Resolution                                                                                |
| :------------------------------------------------------------------- | :----------------------------------------------------- | :---------------------------------------------------------------------------------------- |
| FastAPI initially failed with a missing `schemas` import             | Incorrect startup/module structure during early setup  | Corrected the application startup/import path and used the working `main:app` entry point |
| Qdrant returned `403`                                                | Malformed Qdrant URL/environment configuration         | Corrected the Qdrant configuration                                                        |
| Qdrant returned `404 Collection not found`                           | Expected KB collection was not available               | Reindexed/populated the Qdrant collection                                                 |
| Celery Docker container reported `celery: executable file not found` | Worker runtime did not expose the Celery executable    | Corrected the worker dependency/runtime configuration                                     |
| Redis was required for worker execution                              | Celery broker/backend depends on Redis                 | Started Redis through the local Docker environment                                        |
| Worker required `INCIDENT_HANDLER`                                   | Worker task depends on the configured incident handler | Provided the required environment configuration before starting the worker                |

These issues are included because they represent actual setup and runtime problems encountered while bringing the system into a working state.

---

# 24. Verification Evidence

All verification evidence is stored under:

```text
docs/evidence/
```

The evidence includes ServiceNow configuration, human-review actions, AI write-back, runtime behavior, reliability checks, and automated tests.

### ServiceNow and Human Review

```text
01_ui_policy_record.png
02_ui_policy_actions.png
03_ui_actions_list.png
04_review_actions_visible.png
05_review_actions_hidden.png
06_approve_result.png
07_edit_result.png
08_reject_result.png
09_lifecycle_guard_work_note.png
10_lifecycle_guard_terminal.png
11_confidence_validation.png
12_live_suggest_terminal.png
13_live_suggest_servicenow.png
14_live_escalate.png
```

### Runtime, Reliability, and Testing

```text
15_python_tests_passed.png
celery_fastapi.png
Celery_worker.png
DLQ_inspections.png
Health check.png
requeue_Event.png
Retry_exceed.png
Success_one.png
tests.png
time_limit_test.png
```

---

# 25. Verification Checklist

* [x] Python environment and project dependencies were configured.
* [x] `.env.example` was used as the configuration template.
* [x] Real credentials were kept outside committed files.
* [x] Docker Compose services were started and inspected.
* [x] PostgreSQL was available.
* [x] Redis was available.
* [x] FastAPI started successfully.
* [x] Celery worker started successfully.
* [x] Qdrant configuration was corrected and the KB collection was populated.
* [x] Published KB retrieval was verified.
* [x] ServiceNow webhook authentication and validation were verified.
* [x] Asynchronous processing through Celery was verified.
* [x] Fresh ServiceNow incident retrieval was verified.
* [x] Guardrails were applied before AI processing.
* [x] The ReAct agent used the four supported tools.
* [x] Grounding validation was enforced.
* [x] AI suggestions required human review.
* [x] Approve, Edit, and Reject actions were verified.
* [x] Lifecycle guard behavior was verified.
* [x] Confidence validation was verified.
* [x] ServiceNow suggestion and escalation write-back were verified.
* [x] Retry behavior was verified.
* [x] Dead-letter handling was inspected.
* [x] Event requeue behavior was verified.
* [x] Worker reliability and execution limits were verified.
* [x] Automated tests were executed successfully.
* [x] Verification evidence was committed under `docs/evidence/`.
* [x] No secrets were included in the verification evidence.

---

# 26. Result

The verification confirms that the documented setup, runtime behavior, ServiceNow integration, AI processing flow, reliability mechanisms, and human-review workflow correspond to the implemented project.

The verification evidence stored under:

```text
docs/evidence/
```

provides screenshots covering the relevant configuration, runtime, ServiceNow, reliability, and testing activities.
