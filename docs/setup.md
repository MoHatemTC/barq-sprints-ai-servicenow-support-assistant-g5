# Setup Guide

## 1. Overview

This guide explains how to set up and run the **AI ServiceNow Support Assistant** from a clean machine.

The setup includes:

* Python environment and project dependencies
* Environment variables
* Docker Compose services
* PostgreSQL
* Redis
* Qdrant configuration
* ServiceNow configuration
* LLM configuration
* Knowledge-base ingestion
* First system test

---

# 2. Prerequisites

Before running the project, make sure the following are available:

* Git
* Python 3.12+
* `uv`
* Docker Desktop
* Docker Compose
* A ServiceNow instance
* ServiceNow integration credentials
* Qdrant instance or local Qdrant configuration
* LLM/LiteLLM configuration

The project uses `uv` for Python dependency and environment management.

---

# 3. Clone the Repository

Clone the project repository:

```bash
git clone <repository-url>
cd ai-servicenow-support-assistant-g5
```

---

# 4. Python Environment

Create the project environment using `uv`:

```bash
uv sync
```

This installs the dependencies defined by the project configuration and lock file.

The project can then be executed using `uv run`.

For example:

```bash
uv run uvicorn main:app --reload
```

---

# 5. Environment Variables

Create the local environment file:

```text
.env
```

Use `.env.example` as the template.

Do not commit `.env` or any file containing real credentials.

The application loads configuration from environment variables before initializing its services.

---

## 5.1 ServiceNow Variables

| Variable                    | Purpose                              | Required |
| --------------------------- | ------------------------------------ | -------- |
| `SERVICENOW_URL`            | ServiceNow instance URL              | Yes      |
| `SERVICENOW_USERNAME`       | ServiceNow integration username      | Yes      |
| `SERVICENOW_PASSWORD`       | ServiceNow integration password      | Yes      |
| `SERVICENOW_KB_ID`          | ServiceNow knowledge-base identifier | Yes      |
| `SERVICENOW_KB_CATEGORY_ID` | KB category identifier               | Yes      |

These variables are used by the ServiceNow clients for incident and knowledge-base operations.

---

## 5.2 Webhook Security

| Variable         | Purpose                                                    | Required |
| ---------------- | ---------------------------------------------------------- | -------- |
| `WEBHOOK_SECRET` | Secret used to validate ServiceNow webhook HMAC signatures | Yes      |
| `API_SECRET_KEY` | API key used for protected KB event endpoints              | Yes      |

`WEBHOOK_SECRET` must match the secret used by the ServiceNow webhook integration.

---

## 5.3 Database Variables

The application can configure PostgreSQL through `DATABASE_URL` or individual PostgreSQL environment variables.

| Variable            | Purpose                   |
| ------------------- | ------------------------- |
| `DATABASE_URL`      | PostgreSQL connection URL |
| `POSTGRES_HOST`     | PostgreSQL host           |
| `POSTGRES_PORT`     | PostgreSQL port           |
| `POSTGRES_DB`       | Database name             |
| `POSTGRES_USER`     | Database user             |
| `POSTGRES_PASSWORD` | Database password         |

The project uses PostgreSQL for event tracking and processing state.

---

## 5.4 Redis Variables

| Variable     | Purpose                          | Required |
| ------------ | -------------------------------- | -------- |
| `REDIS_URL`  | Celery broker/backend connection | Yes      |
| `REDIS_PORT` | Redis port                       | Optional |

When running through Docker Compose, the Redis service can be referenced using the Compose service name:

```text
redis://redis:6379/0
```

---

## 5.5 Qdrant Variables

Qdrant stores the knowledge-base vectors used by `searchKB`.

Typical configuration includes:

| Variable            | Purpose                   |
| ------------------- | ------------------------- |
| `QDRANT_URL`        | Qdrant endpoint           |
| `QDRANT_API_KEY`    | Qdrant authentication key |
| `QDRANT_COLLECTION` | Vector collection name    |

The project uses the collection:

```text
kb_baai_bge_base_en_v1_5
```

The configured vector size is:

```text
768
```

---

## 5.6 Embedding Configuration

The project uses:

```text
BAAI/bge-base-en-v1.5
```

through `sentence-transformers`.

The embedding model is used during both KB ingestion and semantic search.

---

## 5.7 LLM Configuration

The project uses `ChatOpenAI` through a LiteLLM-compatible endpoint.

The main configuration includes:

| Variable           | Purpose                 |
| ------------------ | ----------------------- |
| `LITELLM_BASE_URL` | LiteLLM endpoint        |
| `LITELLM_API_KEY`  | LiteLLM API key         |
| `LLM_MODEL`        | Model used by the agent |

The default model configured by the project is:

```text
gemini-2.5-flash
```

The LLM configuration also includes a timeout and retry behavior.

---

# 6. Agent Configuration

The agent has configurable execution and retrieval limits.

Important settings include:

| Setting                      |    Default |
| ---------------------------- | ---------: |
| `TOP_K`                      |          5 |
| `SCORE_THRESHOLD`            |       0.70 |
| Maximum iterations           |          6 |
| Maximum execution time       | 30 seconds |
| Maximum token usage          |     20,000 |
| Maximum KB searches          |          3 |
| Maximum grounding rejections |          2 |

The retrieval threshold controls whether a KB result is considered sufficiently relevant.

The execution limits prevent the ReAct agent from running indefinitely.

---

# 7. Docker Compose

The project provides a Docker Compose configuration for the main infrastructure services.

The Compose environment contains:

```text
FastAPI
Celery Worker
PostgreSQL
Redis
```

The architecture is:

```text
                    ┌──────────────┐
                    │   FastAPI    │
                    │    :8000     │
                    └──────┬───────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
       ┌──────────────┐         ┌──────────────┐
       │  PostgreSQL  │         │    Redis     │
       │    :5432     │         │    :6379     │
       └──────────────┘         └──────┬───────┘
                                       │
                                       ▼
                                ┌──────────────┐
                                │ Celery Worker│
                                └──────────────┘
```

PostgreSQL is exposed on the host using port `5433` while the container uses port `5432`.

Redis uses port `6379`.

---

# 8. Start the Infrastructure

From the project root:

```bash
docker compose up -d
```

Check the running containers:

```bash
docker compose ps
```

The expected services include:

```text
fastapi_app
postgres_db
redis
celery worker
```

Container names may vary depending on the Compose configuration.

---

# 9. Start the FastAPI Application

If running FastAPI directly from the Python environment:

```bash
uv run uvicorn main:app --reload
```

The API should become available on:

```text
http://localhost:8000
```

The FastAPI application exposes the project API endpoints, including the incident webhook and KB-related endpoints.

---

# 10. Start the Celery Worker

The Celery worker is responsible for asynchronous incident processing.

Run:

```bash
celery -A Worker.celery_app:celery_app worker --loglevel=INFO --concurrency=2
```

The worker connects to Redis using `REDIS_URL`.

The worker also loads the incident processing task configuration and reliability settings.

---

# 11. Verify the Application

Once the API is running, open the FastAPI Swagger UI:

```text
http://localhost:8000/docs
```

Use Swagger to verify that the API is reachable and that the expected endpoints are registered.

---

# 12. Database Initialization

On application startup, the database layer initializes the required PostgreSQL tables.

The project uses tables including:

```text
events_log
completed_events
dead_letter_events
```

`events_log` is used for webhook event tracking and incident idempotency.

---

# 13. Knowledge Base Setup

The knowledge-base retrieval system uses Qdrant to store vector representations of published ServiceNow KB content.

The ingestion process is:

```text
ServiceNow KB
      ↓
Fetch published articles
      ↓
Clean HTML
      ↓
Chunk text
      ↓
Generate embeddings
      ↓
Store vectors in Qdrant
```

The embedding model is:

```text
BAAI/bge-base-en-v1.5
```

---

# 14. Run KB Ingestion

The project includes the KB ingestion and reindexing functionality.

The ingestion process handles:

1. Retrieving published KB articles.
2. Cleaning article HTML.
3. Splitting article content into chunks.
4. Generating embeddings.
5. Removing outdated vector data.
6. Upserting the new vectors into Qdrant.

The reindexing entry point is:

```text
reindex.py
```

Run the project's reindex command from the project root according to the configured environment.

After ingestion, verify that the expected Qdrant collection exists:

```text
kb_baai_bge_base_en_v1_5
```

---

# 15. First Webhook Test

The main incident webhook is:

```text
POST /api/webhook
```

The request must contain the ServiceNow signature:

```text
X-ServiceNow-Signature
```

The payload contains:

```json
{
  "sys_id": "0123456789abcdef0123456789abcdef",
  "number": "INC0010001",
  "short_description": "VPN connection problem",
  "description": "The user cannot connect to the company VPN."
}
```

The request body must be signed using the configured `WEBHOOK_SECRET`.

A valid request is accepted asynchronously and returns:

```text
202 Accepted
```

The event is then passed to Redis and processed by the Celery worker.

---

# 16. Webhook Processing Verification

After sending a valid webhook, verify the following sequence:

```text
Webhook received
      ↓
HMAC verified
      ↓
Payload validated
      ↓
Idempotency checked
      ↓
Event stored in PostgreSQL
      ↓
Worker payload queued
      ↓
202 returned
      ↓
Celery worker receives task
      ↓
Fresh incident fetched
      ↓
AI processing starts
```

The Celery worker logs can be used to verify that the task was received and executed.

---

# 17. Verify Knowledge Retrieval

During agent execution, `searchKB` converts the search query into an embedding and searches Qdrant.

The configured retrieval behavior uses:

```text
TOP_K = 5
SCORE_THRESHOLD = 0.70
workflow_state = published
```

If no KB result reaches the configured score threshold, the agent can use `requestHR` instead of generating an unsupported response.

---

# 18. Verify AI Write-back

After successful agent processing, the ServiceNow write-back client updates the permitted AI fields.

A suggestion can include:

```text
AI status
AI confidence
AI suggested response
Human review required
AI processed
```

Internal processing information can also be added through `work_notes`.

The AI does not directly modify protected incident lifecycle fields such as:

```text
state
assigned_to
assignment_group
close_code
close_notes
```

---

# 19. Verify Human Review

After a successful suggestion, the ServiceNow incident should indicate that human review is required.

The reviewer can:

```text
Approve
Edit
Reject
```

The approved or edited response can then become customer-facing communication.

The AI itself does not directly send the final customer-facing response.

---

# 20. Clean Setup Verification

A clean-machine setup should be considered successful when the following are working:

* Python environment created successfully.
* Project dependencies installed.
* Environment variables loaded.
* PostgreSQL starts successfully.
* Redis starts successfully.
* FastAPI starts successfully.
* Celery worker connects to Redis.
* Qdrant collection is available.
* Published KB content is indexed.
* `/api/webhook` accepts a valid signed request.
* Duplicate incidents are detected.
* Worker receives the queued event.
* Agent can retrieve KB content.
* AI result can be written back to ServiceNow.
* Human review can be performed in ServiceNow.

---

# 21. Common Startup Checks

If the FastAPI application fails during startup, check:

```text
1. .env exists
2. Required ServiceNow variables are set
3. DATABASE_URL or PostgreSQL variables are valid
4. Qdrant configuration is valid
5. LLM configuration is valid
```

If the Celery worker fails to start, check:

```text
1. REDIS_URL is set
2. Redis is running
3. Worker task configuration is available
4. INCIDENT_HANDLER is configured
```

If KB retrieval fails, check:

```text
1. Qdrant is reachable
2. The expected collection exists
3. The collection contains vectors
4. The embedding model is available
5. Published KB articles were indexed
```

---

# 22. Environment Summary

The minimum configuration can be grouped as:

```text
ServiceNow
├── SERVICENOW_URL
├── SERVICENOW_USERNAME
├── SERVICENOW_PASSWORD
├── SERVICENOW_KB_ID
└── SERVICENOW_KB_CATEGORY_ID

Security
├── WEBHOOK_SECRET
└── API_SECRET_KEY

Database
└── DATABASE_URL / POSTGRES_*

Queue
└── REDIS_URL

Vector Database
├── QDRANT_URL
└── QDRANT_API_KEY

LLM
├── LITELLM_BASE_URL
├── LITELLM_API_KEY
└── LLM_MODEL
```

Never place real credentials directly in source code or documentation.

---

# 23. Setup Flow Summary

The complete setup can be summarized as:

```text
Clone Repository
       ↓
Create Environment
       ↓
uv sync
       ↓
Configure .env
       ↓
Start PostgreSQL + Redis
       ↓
Configure Qdrant
       ↓
Start FastAPI
       ↓
Start Celery Worker
       ↓
Index Published KB
       ↓
Open Swagger
       ↓
Send Signed Test Webhook
       ↓
Verify Celery Processing
       ↓
Verify KB Retrieval
       ↓
Verify ServiceNow Write-back
       ↓
Verify Human Review
```

After completing these steps, the system is ready for end-to-end incident processing.
