# AI ServiceNow Support Assistant

## Problem Statement

ServiceNow incidents often require support teams to manually search the knowledge base, determine whether the available information is relevant, and prepare a response for the requester.

The **AI ServiceNow Support Assistant** automates the knowledge-search and response-drafting part of this workflow.

When a new incident is received, the system:

1. Receives the incident through a signed webhook.
2. Validates and sanitizes the incident data.
3. Queues the incident for asynchronous processing.
4. Retrieves relevant published knowledge-base content using vector search.
5. Uses a ReAct-based AI agent to reason over the retrieved knowledge.
6. Generates a grounded, cited response when sufficient knowledge is available.
7. Escalates the incident to a human when the available knowledge is insufficient or processing cannot safely continue.
8. Writes the AI result back to ServiceNow for human review.

The AI system does **not** resolve, close, or reassign incidents. Customer-facing communication remains under human control through the ServiceNow review workflow.

---

## System Flow

```text
ServiceNow Incident
        │
        ▼
ServiceNow Business Rule
        │
        │ Signed Webhook
        ▼
POST /api/webhook
        │
        ├── Verify HMAC Signature
        ├── Validate Payload
        └── Check Idempotency
        │
        ▼
PostgreSQL
        │
        ▼
Redis Queue
        │
        ▼
Celery Worker
        │
        ▼
Fetch Fresh Incident from ServiceNow
        │
        ▼
Sanitize / Check Guardrails Again
        │
        ▼
ReAct AI Agent
        │
        ├───────────────┐
        │               │
        ▼               ▼
    searchKB        Other Tools
        │               │
        ▼               ├── addworknote
     Qdrant             ├── suggestAnswer
        │               └── requestHR
        │
        ▼
   Agent Decision
        │
        ├───────────────┐
        │               │
        ▼               ▼
 suggestAnswer      requestHR
        │               │
        └───────┬───────┘
                ▼
      ServiceNow Write-back
                │
                ▼
         Human Review
                │
        ┌───────┼────────┐
        ▼       ▼        ▼
     Approve   Edit    Reject
        │       │        │
        └───────┴────────┘
                │
                ▼
       Customer-facing response
       or Human Escalation
```

The webhook returns `202 Accepted` after the incident is accepted for asynchronous processing. The actual AI processing is handled by the Celery worker.

---

## Tech Stack

| Component              | Technology              | Purpose                                                             |
| ---------------------- | ----------------------- | ------------------------------------------------------------------- |
| API                    | FastAPI                 | Receives ServiceNow webhooks , KB_Events  and exposes API endpoints |
| Background Processing  | Celery                  | Processes incidents asynchronously                                  |
| Message Broker         | Redis                   | Queues background tasks                                             |
| Database               | PostgreSQL              | Stores event state, completed events, and dead-letter events        |
| Vector Database        | Qdrant                  | Stores and searches knowledge-base embeddings                       |
| Embeddings             | `BAAI/bge-base-en-v1.5` | Converts KB content into vectors                                    |
| LLM                    | ChatOpenAI via LiteLLM  | Powers the ReAct agent                                              |
| Default Model          | `gemini-2.5-flash`      | Default configured LLM model                                        |
| Agent                  | Custom ReAct loop       | Controls tool usage and grounded reasoning                          |
| ServiceNow Integration | ServiceNow Table API    | Reads incidents/KB articles and writes AI results                   |
| HTTP Client            | `httpx`                 | Handles ServiceNow API communication                                |
| Containerization       | Docker / Docker Compose | Runs the application services                                       |

---

## AI Agent Tools

The ReAct agent has four tools:

| Tool                                | Purpose                                               |
| ----------------------------------- | ----------------------------------------------------- |
| `searchKB(query)`                   | Searches published knowledge-base content             |
| `addworknote(note)`                 | Adds an internal AI work note to the incident         |
| `suggestAnswer(procedure, sources)` | Submits a grounded, cited response for human approval |
| `requestHR(reason)`                 | Escalates the incident to a human                     |

The AI cannot resolve, close, or reassign an incident.

---

## Knowledge Base

The knowledge base is stored in Qdrant as vector embeddings.

The ingestion flow is:

```text
ServiceNow KB Article
        │
        ▼
Clean HTML
        │
        ▼
Chunk Article
        │
        ▼
Generate Embeddings
        │
        ▼
Store in Qdrant
```

During incident processing:

```text
Incident
   │
   ▼
searchKB(query)
   │
   ▼
Generate Query Embedding
   │
   ▼
Search Qdrant
   │
   ▼
Published + Relevant Chunks
   │
   ▼
ReAct Agent
```

The default retrieval threshold is `0.70`, with a default `TOP_K` of `5`.

---

## Human Review

AI-generated responses are not automatically sent to the customer.

The AI writes its result to dedicated ServiceNow fields, including:

* AI status
* AI confidence
* AI suggested response
* Human review required
* AI processed
* Internal work notes

The fulfiller then reviews the AI suggestion through the ServiceNow Incident form.

Available actions:

* **Approve AI Suggestion**
* **Edit AI Suggestion**
* **Reject AI Suggestion**

Customer-facing communication is written to the `comments` field through the human review actions rather than directly by the AI write-back client.

---

## Security and Reliability

The system includes:

* HMAC-SHA256 webhook signature validation
* Request validation
* Incident sanitization
* Prompt-injection checks
* PostgreSQL idempotency
* Asynchronous Celery processing
* Retry handling for transient ServiceNow failures
* Dead-letter handling for permanently failed tasks
* Agent iteration, time, token, and search limits
* Grounding and citation validation
* ServiceNow write-back field allow-list
* Human approval before customer-facing communication

If the AI cannot safely produce a grounded answer, the system can escalate the incident to a human instead.

---

## Quick Start

### Prerequisites

Before running the project, make sure the following are available:

* Python 3.12
* Docker and Docker Compose
* ServiceNow PDI with the required configuration
* Redis
* PostgreSQL
* Qdrant
* LiteLLM / configured LLM provider

The Docker Compose configuration includes the FastAPI application, Celery worker, PostgreSQL, and Redis. Qdrant is not started as a Compose service and must be provided separately or through Qdrant Cloud.

### 1. Clone the Repository

```bash
git clone <repository-url>
cd <repository-directory>
```

### 2. Configure Environment Variables

Create the environment file from the provided example:

```bash
cp .env.example .env
```

Configure the required ServiceNow, database, Redis, Qdrant, and LLM settings.

**Do not commit real credentials or secrets to the repository.**

For the complete environment-variable reference, see:

[`docs/setup.md`](docs/setup.md)

### 3. Start the Services

```bash
docker compose up --build
```

This starts:

* FastAPI
* Celery worker
* PostgreSQL
* Redis

Qdrant must be configured separately.

### 4. Verify the API

Once the application is running, verify that the FastAPI service is reachable:

```text
http://localhost:8000
```

For the API endpoints and request contracts, see:

[`docs/reference.md`](docs/reference.md)

### 5. Configure ServiceNow

Configure the required ServiceNow application, fields, integration user, Business Rules, UI Actions, and UI Policies.

See:

[`docs/servicenow_setup.md`](docs/servicenow_setup.md)

### 6. Run a Safe Agent Test

The project provides a manual agent test using a fake write-back port:

```bash
python -m scripts.try_agent "wifi keeps disconnecting on my laptop"
```

This allows the agent to use the real LLM and Qdrant without writing to a real ServiceNow incident.

Generate evidence with:

```bash
python -m scripts.make_evidence
```

---

## Documentation

| Document                                                                 | Description                                                     |
| ------------------------------------------------------------------------ | --------------------------------------------------------------- |
| [`docs/architecture.md`](docs/architecture.md)                           | Detailed end-to-end architecture and component responsibilities |
| [`docs/setup.md`](docs/setup.md)                                         | Clean-machine setup and environment configuration               |
| [`docs/servicenow_setup.md`](docs/servicenow_setup.md)                   | ServiceNow application and configuration                        |
| [`docs/reference.md`](docs/reference.md)                                 | API, webhook, Celery, agent, KB, and write-back contracts       |
| [`docs/troubleshooting.md`](docs/troubleshooting.md)                     | Common operational failures and resolutions                     |
| [`docs/decisions_and_limitations.md`](docs/decisions_and_limitations.md) | Architecture decisions and known limitations                    |
| [`docs/verification.md`](docs/verification.md)                           | Clean-environment verification and execution evidence           |

---

## Project Structure

```text
.
├── App/
├── Routes/
├── Schemas/
├── Services/
├── Clients/
├── Worker/
├── agent/
├── src/
│   ├── agent/
│   └── writeback/
├── servicenow/
├── Scripts/
├── tests/
├── docs/
│   └── evidence/
├── main.py
├── run_pipeline.py
├── reindex.py
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── pyproject.toml
└── uv.lock
```

---

## Testing

Run the Python test suite:

```bash
python -m pytest
```

The project includes tests for:

* Agent behavior
* Agent loop
* Tools
* Write-back
* Worker processing
* Response formatting
* Document retrieval
* PDF parsing contracts
* ServiceNow script behavior

For the complete verification procedure, see:

[`docs/verification.md`](docs/verification.md)

---

## Known Limitations

The current implementation has several known limitations:

* Qdrant is not included as a Docker Compose service.
* Some ServiceNow-side outbound configuration exists outside the repository.
* AI confidence represents the highest retrieval similarity score and is not a calibrated probability of correctness.
* Prompt-injection detection includes keyword-based checks.
* Incident idempotency uses the incident `sys_id`.

More details are documented in:

[`docs/decisions_and_limitations.md`](docs/decisions_and_limitations.md)
