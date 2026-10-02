# Component & Interface Reference

## 1. Overview

This document is the technical reference for the main interfaces and runtime components of the **AI ServiceNow Support Assistant**.

It documents the contracts that connect:

* ServiceNow and the FastAPI webhook.
* FastAPI and the Celery/Redis worker.
* The Celery worker and the ReAct agent.
* The ReAct agent and its four tools.
* ServiceNow Knowledge Base and Qdrant.
* The AI agent and the ServiceNow write-back client.
* The worker and the PostgreSQL event state.

---

# 2. Incident Webhook

## 2.1 Endpoint

```text
POST /api/webhook
```

The endpoint is the main entry point for ServiceNow incident events.

The endpoint is designed to acknowledge the event quickly and perform the expensive AI processing asynchronously.

```text
ServiceNow
    │
    │ POST /api/webhook
    ▼
FastAPI
    │
    ├── Authenticate
    ├── Validate
    ├── Idempotency
    ├── Guardrails
    │
    └── Queue worker
             │
             ▼
          HTTP 202
```

No LLM processing is performed inside the webhook request.

---

## 2.2 Authentication

The webhook requires:

```text
X-ServiceNow-Signature
```

The signature is generated using:

```text
HMAC-SHA256
```

and the shared secret configured as:

```text
WEBHOOK_SECRET
```

The backend verifies the signature against the raw request body.

The implementation accepts the supported hexadecimal/base64 signature representations and compares them using constant-time comparison.

---

## 2.3 Request Payload

The expected JSON payload is:

```json
{
  "sys_id": "0123456789abcdef0123456789abcdef",
  "number": "INC0010001",
  "short_description": "VPN connection problem",
  "description": "The user cannot connect to the company VPN."
}
```

### Fields

| Field               | Type   | Validation                        |
| ------------------- | ------ | --------------------------------- |
| `sys_id`            | string | Exactly 32 hexadecimal characters |
| `number`            | string | Must match `INC\d+`               |
| `short_description` | string | 1–4000 characters                 |
| `description`       | string | Maximum 100,000 characters        |

The request is validated using the `IncidentPayload` Pydantic schema.

---

## 2.4 Response Status Codes

### `202 Accepted`

Returned when the event passes the synchronous checks and is successfully queued for asynchronous processing.

Example:

```json
{
  "status": "accepted",
  "event_id": "..."
}
```

`202` means the backend accepted the event for processing. It does not mean that the AI processing or ServiceNow write-back has already completed.

### `401 Unauthorized`

Returned when the webhook authentication fails.

Examples:

* Missing `X-ServiceNow-Signature`.
* Invalid signature.

### `422 Unprocessable Entity`

Returned when the JSON payload does not satisfy the `IncidentPayload` schema.

Examples:

* Invalid `sys_id`.
* Invalid incident number.
* Missing required fields.
* Field length exceeds its configured limit.

### `500 Internal Server Error`

Returned when the backend itself is incorrectly configured or an unexpected error occurs.

For example, a missing `WEBHOOK_SECRET` is treated as a server configuration error.

---

# 3. Webhook Processing Contract

The webhook processing sequence is:

```text
Request
  ↓
HMAC verification
  ↓
Pydantic validation
  ↓
events_log insertion
  ↓
Guardrails
  ↓
Minimal WorkerPayload
  ↓
Celery .delay()
  ↓
202 Accepted
```

The object sent to Redis/Celery is intentionally small:

```json
{
  "event_id": "...",
  "sys_id": "...",
  "number": "INC0010001",
  "received_at": "..."
}
```

The incident description is not placed directly in the queue payload.

The worker fetches a fresh copy from ServiceNow instead.

---

# 4. Idempotency

Idempotency is implemented using PostgreSQL.

The incoming event is recorded in:

```text
events_log
```

The ServiceNow incident `sys_id` is unique in this table.

If the same incident is received again:

```text
Duplicate sys_id
      ↓
UNIQUE constraint
      ↓
duplicate_ignored
      ↓
No second worker job
```

Example response:

```json
{
  "status": "duplicate_ignored"
}
```

This prevents the same incident from creating multiple processing jobs.

---

# 5. PostgreSQL Event State

The database creates three project tables.

| Table                | Purpose                                 |
| -------------------- | --------------------------------------- |
| `events_log`         | Incoming event records and idempotency  |
| `completed_events`   | Successfully completed event processing |
| `dead_letter_events` | Permanently failed events               |

The normal lifecycle is:

```text
events_log
    │
    ├── successful processing ──→ completed_events
    │
    └── permanent failure ──────→ dead_letter_events
```

---

# 6. Celery Worker

## 6.1 Task

The main incident processing task is:

```text
process_incident_worker
```

It is implemented in:

```text
Worker/tasks.py
```

The worker receives the minimal `WorkerPayload` and performs the slow processing outside the HTTP request.

---

## 6.2 Worker Processing

The worker:

1. Validates the worker payload.
2. Checks whether the event was already completed.
3. Fetches the latest incident from ServiceNow.
4. Handles retryable/permanent ServiceNow errors.
5. Runs the guardrails again.
6. Calls the incident handler.
7. Runs the AI pipeline.
8. Writes the AI result back to ServiceNow.
9. Marks the event as completed when processing succeeds.

---

# 7. ServiceNow Incident Fetch

The worker retrieves the current incident using:

```text
GET {SERVICENOW_INSTANCE_URL}/api/now/table/incident/{sys_id}
```

The ServiceNow request uses:

```text
Basic Authentication
```

with:

```text
SERVICENOW_USERNAME
SERVICENOW_PASSWORD
```

The HTTP client uses a timeout.

### Error classification

| Failure       | Handling          |
| ------------- | ----------------- |
| Network error | Retryable         |
| Timeout       | Retryable         |
| `429`         | Retryable         |
| `5xx`         | Retryable         |
| Other `4xx`   | Permanent failure |

---

# 8. Celery Retry Policy

The incident task is configured with:

```text
max_retries = 2
```

Retryable failures use exponential backoff with jitter.

Conceptually:

```text
Retry delay = 2 × 2^n + jitter
```

If the retry limit is reached, the event is sent to the dead-letter flow.

Permanent failures are sent to the DLQ without retrying.

---

# 9. Celery Reliability Configuration

The Celery worker uses:

```text
task_acks_late = True
task_reject_on_worker_lost = True
worker_prefetch_multiplier = 1
```

The task time limits are:

```text
Soft limit: 60 seconds
Hard limit: 90 seconds
```

Redis visibility timeout is:

```text
120 seconds
```

These settings are intended to reduce message loss and support redelivery when a worker process crashes.

---

# 10. Dead Letter Queue

The project uses PostgreSQL for the dead-letter event store.

A permanently failed event is recorded in:

```text
dead_letter_events
```

The stored information includes the event payload, error information, and attempt count.

Examples of DLQ conditions include:

* Permanent ServiceNow `4xx` errors.
* Retryable ServiceNow failures after all retries are exhausted.
* Other worker-level failures routed through the dead-letter handler.

---

# 11. ReAct Agent

The main agent is implemented as a custom ReAct loop using LangChain tool binding.

The agent has exactly four registered tools:

```text
searchKB
addworknote
suggestAnswer
requestHR
```

The tool registry verifies that the registered tool set contains exactly these four tools.

---

# 12. Agent Runtime Limits

The agent has configurable limits.

Default values are:

| Limit                        |       Default |
| ---------------------------- | ------------: |
| Maximum iterations           |             6 |
| Maximum execution time       |    30 seconds |
| Maximum token usage          | 20,000 tokens |
| Maximum KB searches          |             3 |
| Maximum grounding rejections |             2 |
| LLM retries                  |             2 |
| LLM retry base delay         |      1 second |

These values can be overridden through the `AGENT_*` environment variables.

The purpose of these limits is to prevent an agent run from continuing indefinitely.

---

# 13. Agent Execution Model

The basic ReAct cycle is:

```text
LLM
 ↓
Tool call
 ↓
Tool observation
 ↓
LLM
 ↓
Tool call
 ↓
Tool observation
 ↓
...
 ↓
Terminal tool
```

The agent must finish with one of the terminal tools:

```text
suggestAnswer
```

or:

```text
requestHR
```

The agent cannot directly perform arbitrary ServiceNow operations.

---

# 14. `searchKB`

### Purpose

Search the Qdrant knowledge base for relevant published knowledge.

### Input

```text
query
```

Example:

```json
{
  "query": "VPN connection keeps disconnecting"
}
```

### Processing

```text
Query
  ↓
BAAI/bge-base-en-v1.5 embedding
  ↓
Qdrant search
  ↓
Published-only filter
  ↓
Top-K results
  ↓
Score threshold
  ↓
Observation
```

The default retrieval configuration is:

```text
TOP_K = 5
SCORE_THRESHOLD = 0.70
```

Only published KB content is eligible for retrieval.

### Observation

The tool returns an observation containing information such as:

```text
best_score
threshold_met
chunks
status
```

Possible status values include:

```text
success
no_results
error
```

Retrieval errors are returned as observations rather than automatically crashing the agent.

---

# 15. KB Grounding

A suggestion cannot be accepted merely because the LLM generated a plausible answer.

The suggestion must be grounded in retrieved KB content.

The grounding checks include:

* Numbered resolution steps.
* Citation on each step.
* Citation IDs must correspond to actually retrieved articles/chunks.
* Retrieved content must satisfy the configured score threshold.

If the grounding check fails, `suggestAnswer` is rejected.

The agent may continue searching while it remains within its configured limits.

After the grounding rejection limit is reached, the agent falls back to human review.

---

# 16. `addworknote`

### Purpose

Add an internal AI work note to the ServiceNow incident.

This is intended for internal incident-processing information and is separate from customer-facing communication.

### Input

```text
note
```

The note must:

* Be non-empty.
* Be at most 4000 characters.

Example:

```json
{
  "note": "AI escalation reason: No published KB result met the configured grounding threshold."
}
```

The tool calls the write-back port:

```text
add_work_note()
```

A write-back failure is returned as a tool error and can stop the run when the failure is classified as a write-back failure.

---

# 17. `suggestAnswer`

### Purpose

Submit a grounded AI resolution suggestion to ServiceNow.

### Inputs

```text
procedure
sources
```

The procedure must satisfy the numbered-step format.

Each step must contain a valid citation to retrieved knowledge.

Example structure:

```text
1. Restart the VPN client. [Article: KB0010001]
2. Reconnect using the corporate VPN profile. [Article: KB0010001]
```

The tool:

1. Validates the numbered procedure.
2. Validates citations.
3. Calculates AI confidence from retrieval scores.
4. Sets human review as required.
5. Calls the ServiceNow write-back client.
6. Marks the agent run as finished after successful write-back.

The tool does not directly write customer-facing comments.

---

# 18. `requestHR`

### Purpose

Hand the incident to a human when the agent cannot safely provide a grounded answer.

### Input

```text
reason
```

The reason must contain at least:

```text
5 characters
```

The tool calculates the available confidence and sends the escalation through the write-back port.

The resulting ServiceNow state includes:

```text
ai_status = escalated
human_review_required = true
ai_processed = true
```

The escalation reason is recorded as an internal work note.

---

# 19. Agent Tool Summary

| Tool            | Input                  | Main operation                    | Terminal? |
| --------------- | ---------------------- | --------------------------------- | --------- |
| `searchKB`      | `query`                | Search published Qdrant knowledge | No        |
| `addworknote`   | `note`                 | Add internal work note            | No        |
| `suggestAnswer` | `procedure`, `sources` | Write grounded suggestion         | Yes       |
| `requestHR`     | `reason`               | Escalate to human review          | Yes       |

The agent is restricted to these four tools.

---

# 20. Knowledge Base API

## 20.1 Get Published Articles

```text
GET /articles/all
```

This endpoint retrieves published ServiceNow KB articles.

The ServiceNow query filters the `kb_knowledge` table by:

```text
workflow_state=published
```

The request uses the configured ServiceNow integration credentials.

The retrieved records contain the knowledge information required by the ingestion pipeline.

---

# 21. KB Event Endpoint

```text
POST /articles/events
```

This endpoint receives KB change events from ServiceNow.

Authentication uses:

```text
X-API-Key
```

The expected value is:

```text
API_SECRET_KEY
```

---

# 22. KB Event Operations

Supported operations are:

```text
insert
update
delete
retire
```

The behavior is:

| Operation | Action                     |
| --------- | -------------------------- |
| `insert`  | Ingest article into Qdrant |
| `update`  | Re-ingest article          |
| `delete`  | Remove article vectors     |
| `retire`  | Remove article vectors     |

This keeps the Qdrant collection synchronized with the ServiceNow knowledge base.

---

# 23. KB Event Payload

The clean ingestion contract is represented by:

```text
KBIngestionPayload
```

The main fields are:

```text
article_id
title
text
workflow_state
category
```

ServiceNow display/value wrappers are normalized before ingestion.

Published and retired states are supported by the KB event schema.

---

# 24. KB Ingestion Pipeline

The ingestion flow is:

```text
ServiceNow KB
      ↓
Clean HTML
      ↓
Chunk text
      ↓
Generate embeddings
      ↓
Delete old article vectors
      ↓
Upsert new vectors
      ↓
Qdrant
```

The current ingestion configuration uses:

```text
Chunk size: 40 words
Chunk overlap: 1
Embedding model: BAAI/bge-base-en-v1.5
```

Each chunk retains article identity and relevant metadata.

---

# 25. Qdrant Retrieval Contract

The Qdrant collection uses vector size:

```text
768
```

The current collection name is based on the embedding model:

```text
kb_baai_bge_base_en_v1_5
```

Retrieval filters knowledge to:

```text
workflow_state = published
```

The search returns similarity scores that are later used for:

* Grounding decisions.
* AI confidence calculation.
* Citation context.

---

# 26. ServiceNow Write-back Client

The main write-back implementation is:

```text
src/writeback/servicenow_writeback.py
```

It communicates with the ServiceNow Incident Table API:

```text
PATCH /api/now/table/incident/{sys_id}
```

The client validates the incident ID, payload values, and allowed fields before sending the request.

---

# 27. Write-back Allow-list

The AI is allowed to write only to:

```text
x_2216229_sprint_1_ai_status
x_2216229_sprint_1_ai_confidence
x_2216229_sprint_1_ai_suggested_response
x_2216229_sprint_1_human_review_required
x_2216229_sprint_1_ai_processed
work_notes
```

The following fields are intentionally excluded:

```text
state
assigned_to
assignment_group
close_code
close_notes
comments
```

This prevents the AI from directly controlling incident lifecycle or customer-facing communication.

---

# 28. Suggest Write-back

The `suggest()` operation performs one atomic PATCH containing:

```text
ai_status = suggested
ai_suggested_response = <suggested response>
ai_confidence = <confidence>
human_review_required = true
ai_processed = true
```

The suggestion is therefore stored in ServiceNow while waiting for human review.

---

# 29. Escalation Write-back

The `escalate()` operation performs one atomic PATCH containing:

```text
ai_status = escalated
ai_suggested_response = empty
human_review_required = true
ai_processed = true
work_notes = "AI escalation reason: ..."
```

The confidence value is also included when available.

---

# 30. Write-back Retry Policy

The write-back client treats the following HTTP statuses as transient:

```text
429
500
502
503
504
```

Network and timeout failures are also treated as transient.

The default retry sequence uses bounded exponential backoff:

```text
1 second
2 seconds
4 seconds
```

Other HTTP errors are returned without retrying.

Expected operational failures are returned as structured results such as:

```json
{
  "ok": false,
  "error": "..."
}
```

rather than being allowed to crash the service.

---

# 31. Human Review Interface

The AI suggestion is reviewed in ServiceNow.

The available UI actions are:

```text
Approve AI Suggestion
Edit AI Suggestion
Reject AI Suggestion
```

### Approve

Copies the AI suggestion into customer-facing:

```text
comments
```

and clears the human-review flag.

### Edit

Copies the suggestion into `comments` and allows the fulfiller to modify the response before saving.

### Reject

Rejects the AI suggestion, clears the review flag, changes the AI status to:

```text
escalated
```

and adds an internal work note.

---

# 32. Human Review vs AI Write-back

The separation is intentional:

```text
AI
 ↓
AI Suggested Response
 ↓
Human Review
 ↓
comments
 ↓
Customer
```

The AI write-back client itself does not write to `comments`.

This ensures that customer-facing communication remains under human control.

---

# 33. Complete Interface Flow

The main runtime interfaces connect as follows:

```text
ServiceNow Incident
        │
        │ POST /api/webhook
        ▼
FastAPI
        │
        ├── HMAC
        ├── Pydantic
        ├── PostgreSQL idempotency
        └── Guardrails
        │
        ▼
Redis
        │
        ▼
Celery
        │
        ▼
ServiceNow GET
        │
        ▼
ReAct Agent
        │
        ├── searchKB ───────► Qdrant
        │
        ├── addworknote ────► ServiceNow
        │
        ├── suggestAnswer ──► ServiceNow
        │
        └── requestHR ──────► ServiceNow
                                  │
                                  ▼
                            Human Review
                                  │
                         ┌────────┼────────┐
                         ▼        ▼        ▼
                      Approve    Edit     Reject
                         │        │        │
                         └────────┴────────┘
                                  │
                                  ▼
                         Human-controlled outcome
```

---

# 34. Runtime Limits Summary

For quick reference:

| Component                | Limit / Rule                  |
| ------------------------ | ----------------------------- |
| Webhook                  | No model execution in request |
| Incident payload         | `short_description` ≤ 4000    |
| Incident description     | ≤ 100,000                     |
| Guardrail text           | 4000 characters               |
| KB Top-K                 | 5                             |
| KB score threshold       | 0.70                          |
| Agent iterations         | 6                             |
| Agent execution time     | 30 seconds                    |
| Agent tokens             | 20,000                        |
| Agent KB searches        | 3                             |
| Grounding rejections     | 2                             |
| Agent LLM retries        | 2                             |
| Work note                | ≤ 4000 characters             |
| HR reason                | ≥ 5 characters                |
| Celery retries           | 2                             |
| Celery soft time limit   | 60 seconds                    |
| Celery hard time limit   | 90 seconds                    |
| Redis visibility timeout | 120 seconds                   |
| Write-back retry backoff | 1 / 2 / 4 seconds             |

---

# 35. Key Runtime States

The important event states can be understood as:

```text
accepted
   ↓
queued
   ↓
processing
   ↓
completed
```

Failure paths can result in:

```text
failed
dead_lettered
```

AI processing itself can produce:

```text
suggested
```

or:

```text
escalated
```

These are separate concerns:

* Event/database state tracks backend processing.
* AI status tracks the AI result stored on the ServiceNow Incident.

---

# 36. Source of Truth

The major runtime responsibilities are separated as follows:

| Responsibility                | Component                    |
| ----------------------------- | ---------------------------- |
| Receive incident event        | FastAPI                      |
| Authenticate webhook          | HMAC                         |
| Validate payload              | Pydantic                     |
| Idempotency                   | PostgreSQL                   |
| Queue processing              | Redis                        |
| Background execution          | Celery                       |
| Fresh incident data           | ServiceNow Table API         |
| Knowledge retrieval           | Qdrant                       |
| Embeddings                    | BAAI/bge-base-en-v1.5        |
| Reasoning                     | ReAct agent + LLM            |
| AI result write-back          | ServiceNowWritebackClient    |
| Customer-facing communication | Human reviewer in ServiceNow |
| Completed event tracking      | PostgreSQL                   |
| Permanent failure tracking    | PostgreSQL DLQ               |

This separation keeps the HTTP layer fast, the worker responsible for asynchronous processing, the agent restricted to its approved tools, and ServiceNow responsible for the incident record and human review workflow.
