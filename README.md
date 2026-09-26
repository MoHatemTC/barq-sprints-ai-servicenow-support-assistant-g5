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

### 3. Set up the environment

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
