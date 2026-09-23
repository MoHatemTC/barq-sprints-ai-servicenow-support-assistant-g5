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

Commit all three files together: `pyproject.toml`, `uv.lock`, `requirements.txt`.

### 3. Set up your environment file

Copy the example file and fill it in:

```bash
cp .env.example .env
```

### 4. Fill in the ServiceNow credentials

These five are required before anything else will work — get them from your PDI:

| Variable | Where to get it |
|---|---|
| `SERVICENOW_INSTANCE_URL` | Your PDI's base URL, e.g. `https://devXXXXXX.service-now.com` (no trailing slash) |
| `SERVICENOW_USERNAME` | The dedicated **integration user** you created (least-privilege — never the admin account) |
| `SERVICENOW_PASSWORD` | That integration user's password |
| `SERVICENOW_KB_ID` | Open your Knowledge Base record → click the **(i)** info icon in the top-left of the form → copy the **Sys ID** shown |
| `SERVICENOW_KB_CATEGORY_ID` | Same (i)-icon trick, but on the KB **Category** record you're scoping articles to |

Leave the rest (Langfuse, Langsmith, Qdrant, Postgres, LLM/agent config) for when you get to those parts.

Set a unique `WEBHOOK_SECRET` in `.env` and configure the same value in
ServiceNow. Requests without a valid `X-ServiceNow-Signature` are rejected.

## Running the application locally

Start only PostgreSQL through Docker Compose:

```bash
docker compose up -d postgres_db
```

Then run FastAPI locally from the project root:

```bash
uv run uvicorn main:app --reload
```

FastAPI connects to PostgreSQL through `localhost:5433`. The database and the
`events_log` table are created automatically on the first startup.

To run the complete application in Docker later:

```bash
docker compose up --build
```