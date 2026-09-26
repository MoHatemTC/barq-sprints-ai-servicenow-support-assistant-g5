# barq-sprints-ai-servicenow-support-assistant-g5

An event-driven, RAG-powered ServiceNow assistant that retrieves trusted knowledge, drafts cited resolutions, and routes responses for human approval.

## Getting started

### 1. Install `uv`

Dependencies are managed via `uv` and `pyproject.toml`. If you don't have `uv` installed:

**macOS / Linux**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell)**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Verify it installed:

```bash
uv --version
```

### 2. Install dependencies

From the project root (where `pyproject.toml` lives):

```bash
uv sync
```

This creates a `.venv`, resolves dependencies from `pyproject.toml`, and installs them. If no `uv.lock` exists yet, this first run generates one — commit it afterwards so everyone builds from the same resolved versions.

#### Updating dependencies

`pyproject.toml` is the source of truth. `requirements.txt` is generated from it — never edit it by hand.

After adding, removing, or changing a package:

```bash
uv add <package>
# or edit pyproject.toml, then:
uv lock

uv export --no-hashes --emit-index-url --format requirements-txt -o requirements.txt
```

Commit all three files together:

```text
pyproject.toml
uv.lock
requirements.txt
```

### 3. Set up your environment file

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

### 4. Fill in the ServiceNow credentials

These five are required before anything else will work — get them from your PDI:

| Variable                    | Where to get it                                                                                                       |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `SERVICENOW_INSTANCE_URL`   | Your PDI's base URL, e.g. `https://devXXXXXX.service-now.com` (no trailing slash)                                     |
| `SERVICENOW_USERNAME`       | The dedicated **integration user** you created (least-privilege — never the admin account)                            |
| `SERVICENOW_PASSWORD`       | That integration user's password                                                                                      |
| `SERVICENOW_KB_ID`          | Open your Knowledge Base record → click the **(i)** info icon in the top-left of the form → copy the **Sys ID** shown |
| `SERVICENOW_KB_CATEGORY_ID` | Same (i)-icon method, but on the KB **Category** record you're scoping articles to                                    |

Leave the rest (Langfuse, LangSmith, Qdrant, Postgres, LLM/agent config) for when you get to those parts.

Set a unique `WEBHOOK_SECRET` in `.env` and configure the same value in ServiceNow.

Requests without a valid `X-ServiceNow-Signature` are rejected.

## Running the application locally

Start only PostgreSQL through Docker Compose:

```bash
docker compose up -d postgres_db
```

Then run FastAPI locally from the project root:

```bash
uv run uvicorn main:app --reload
```

FastAPI connects to PostgreSQL through `localhost:5433`. The database and the `events_log` table are created automatically on the first startup.

To run the complete application in Docker later:

```bash
docker compose up --build
```

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
| AI confidence            | `x_2216229_sprint_1_ai_confidence`         | Written by `suggest()`                                                            |
| AI suggested response    | `x_2216229_sprint_1_ai_suggested_response` | Written by `suggest()`; read-only on the form                                     |
| Human review flag        | `x_2216229_sprint_1_human_review_required` | Set by `suggest()` and cleared by the human-review/lifecycle workflow             |
| AI processed flag        | `x_2216229_sprint_1_ai_processed`          | Set by `suggest()`                                                                |
| Internal work notes      | `work_notes`                               | Used for AI escalation and internal review notes                                  |
| Customer-facing comments | `comments`                                 | Not written directly by the AI client; populated through the human review actions |

The Python write-back client enforces an explicit field allow-list before every PATCH request. Any field outside the allow-list is rejected before an HTTP request is sent to ServiceNow.

Sensitive Incident fields such as `state`, `assigned_to`, `assignment_group`, `close_code`, and `close_notes` are intentionally excluded from the AI write-back allow-list.

### Atomic Write-back

`suggest()` and `escalate()` update the required AI fields and work notes through a single ServiceNow PATCH request.

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
   * Copies the AI suggestion into the customer-facing `comments` field.
   * Clears `human_review_required`.
   * Saves the incident.

2. **Edit AI Suggestion**

   * Available under the same review conditions.
   * Copies the AI suggestion into `comments`.
   * Allows the fulfiller to review and modify the customer-facing response before saving.

3. **Reject AI Suggestion**

   * Available when the AI status is `suggested` and human review is required.
   * Clears `human_review_required`.
   * Changes `ai_status` to `escalated`.
   * Adds an internal work note documenting the rejection.
   * Saves the incident.

No separate ServiceNow "Escalate"
