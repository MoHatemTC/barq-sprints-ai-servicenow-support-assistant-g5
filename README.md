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
uv add <package>          # or edit pyproject.toml, then: uv lock
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

Sprint 3 (S3.6) adds the ServiceNow write-back client and human review
surface for AI-generated incident suggestions.

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
Customer-facing communication is performed by the human fulfiller through
the ServiceNow review UI.

### Atomic Write-back

`suggest()` and `escalate()` update the required AI fields and work notes
through a single ServiceNow PATCH request.

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

No separate ServiceNow "Escalate" UI Action is required. Escalation is exposed
through the Python write-back client and the Reject human-review workflow.

### AI Fields Read-only Policy

ServiceNow UI Policy:

`AI Fields Read Only`

The following five AI-managed fields are read-only on the Incident form:

* `x_2216229_sprint_1_ai_status`
* `x_2216229_sprint_1_ai_confidence`
* `x_2216229_sprint_1_ai_suggested_response`
* `x_2216229_sprint_1_human_review_required`
* `x_2216229_sprint_1_ai_processed`

Export/documentation:

`servicenow/ui_policies/AI_Fields_Read_Only.js`

### Business Rules

#### AI Lifecycle Guard

`servicenow/business_rules/AI_Lifecycle_Guard.js`

The lifecycle guard clears the human-review flag when:

* a fulfiller adds an internal work note, or
* the incident moves to Resolved, Closed, or Canceled.

AI-generated escalation work notes are ignored by the guard so that the
AI escalation itself does not immediately clear the review state.

#### AI Confidence Validation

`servicenow/business_rules/AI_Confidence_Validation.js`

The AI confidence value is validated server-side and must be within:

```text
0.0 <= ai_confidence <= 1.0
```

Empty confidence values are allowed.

### ServiceNow Configuration Exports

```text
servicenow/
├── business_rules/
│   ├── AI_Confidence_Validation.js
│   └── AI_Lifecycle_Guard.js
├── ui_actions/
│   ├── AI_Approve.js
│   ├── AI_Edit.js
│   └── AI_Reject.js
└── ui_policies/
    └── AI_Fields_Read_Only.js
```

These files document the corresponding ServiceNow configuration used by
the S3.6 implementation.

### Tests

Python write-back tests are located at:

`tests/test_writeback.py`

Delivery evidence and screenshots are maintained separately under:

`docs/evidence/`
