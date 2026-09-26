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

---

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

## 🛠️ Sprint 3.3: Agent Tool Layer (`searchKB`, `addworknote`, `suggestAnswer`, `requestHR`)

The agent tool layer provides a secure, sandboxed set of exactly four tools bound to an incident run context (`sys_id`, `number`). In strict alignment with enterprise governance and zero-privilege security, no capabilities exist to resolve, close, or reassign incidents. All outputs remain in draft/advisory status (`human_review_required: true`).

### 1. Tool Contracts & Signatures

| Tool | Type | Signature | Description & Contract |
|---|---|---|---|
| **`searchKB`** | **Non-terminal** | `searchKB(query: str) -> dict` | Executes dense vector similarity search against Qdrant using the configured embedding model (`bge-base-en-v1.5`). Filters by default to `workflow_state == "published"`, applies `SCORE_THRESHOLD`, records retrieval state in `RunContext`, and returns matching chunks. |
| **`addworknote`** | **Non-terminal** | `addworknote(note: str) -> dict` | Validates note length (`1 <= len <= MAX_NOTE_LENGTH`), records note in `RunContext`, and posts the note via the `WriteBackPort.add_work_note`. |
| **`suggestAnswer`** | **Terminal** | `suggestAnswer(procedure: str, sources: list[str] = None) -> dict` | Validates that `procedure` is a numbered list and each step includes an inline citation `[Article: KBxxxxxxx]`. Verifies that all cited sources were actually retrieved in this run (anti-hallucination guarantee). Calculates `ai_confidence` from retrieval scores, posts to `WriteBackPort.suggest`, and locks the run (`is_finished = True`). |
| **`requestHR`** | **Terminal** | `requestHR(reason: str) -> dict` | Validates non-empty escalation reason (`len >= MIN_REASON_LENGTH`), builds escalation payload with `ai_confidence = RunContext.best_score`, dispatches to `WriteBackPort.escalate`, and locks the run (`is_finished = True`). |

### 2. State & Terminal Semantics

* **State Isolation**: Every tool call is bound to an isolated `RunContext(sys_id, number)` instance.
* **Terminal Lock**: When a terminal tool (`suggestAnswer` or `requestHR`) executes successfully, `run_context.is_finished` is set to `True`. Subsequent calls to **any** tool immediately return a structured `RUN_ALREADY_FINISHED` error observation.
* **Retry on Failure**: If a write-back operation fails (e.g., ServiceNow API network timeout), the run context remains open (`is_finished = False`), enabling the agent to retry without crashing.
* **Exception Safety**: All tool failures are caught and surfaced as structured observations rather than unhandled Python exceptions.

### 3. Observation Schemas

#### A. `searchKB` Observations
```json
// Success with matching chunks
{
  "status": "success",
  "query": "wifi keeps dropping",
  "count": 1,
  "best_score": 0.8521,
  "threshold": 0.70,
  "chunks": [
    {
      "article_id": "KB0010001",
      "title": "Fix WiFi Disconnections",
      "content": "Forget the network and reconnect...",
      "score": 0.8521,
      "workflow_state": "published"
    }
  ]
}

// No chunks above threshold
{
  "status": "no_results",
  "query": "coffee machine broken",
  "count": 0,
  "best_score": 0.3812,
  "threshold": 0.70,
  "message": "No knowledge article scored above threshold 0.7 (best: 0.3812).",
  "chunks": []
}
```

#### B. `addworknote` Observation
```json
{
  "status": "success",
  "message": "Work note added to incident INC0010001.",
  "incident_number": "INC0010001",
  "note_length": 45,
  "port_result": { "status": "success", "operation": "add_work_note" }
}
```

#### C. `suggestAnswer` Observation
```json
{
  "status": "success",
  "message": "Suggested resolution submitted for incident INC0010001.",
  "incident_number": "INC0010001",
  "ai_confidence": 0.8521,
  "citations": ["KB0010001"],
  "payload": {
    "ai_suggested_response": "Suggested resolution (pending human approval):\n1. Forget the network. [Article: KB0010001]\n\nSources:\n- KB0010001",
    "ai_confidence": 0.8521,
    "human_review_required": true,
    "escalated": false,
    "citations": ["KB0010001"]
  }
}
```

#### D. Terminal Block Error Observation
```json
{
  "status": "error",
  "code": "RUN_ALREADY_FINISHED",
  "error": "Incident run INC0010001 is already finished. No further tool executions are permitted."
}
```

### 4. Central Configuration Parameters

All parameters are centralized in `agent/config.py` and configurable via `.env`:

| Parameter | Environment Variable | Default | Purpose |
|---|---|---|---|
| `TOP_K` | `TOP_K` | `5` | Maximum number of nearest vector chunks returned by Qdrant. |
| `SCORE_THRESHOLD` | `SCORE_THRESHOLD` | `0.70` | Minimum cosine similarity required to accept a retrieved chunk. |
| `MAX_NOTE_LENGTH` | `MAX_NOTE_LENGTH` | `4000` | Maximum character length for internal work notes. |
| `MIN_REASON_LENGTH` | `MIN_REASON_LENGTH` | `5` | Minimum character length for human escalation reasons. |
| `ALLOWED_WORKFLOW_STATES` | `ALLOWED_WORKFLOW_STATES` | `published` | Comma-separated list of KB states eligible for retrieval. |
| `EMBEDDING_MODEL_NAME` | `EMBEDDING_MODEL_NAME` | `BAAI/bge-base-en-v1.5` | SentenceTransformer model used for dense retrieval. |
| `EMBEDDING_VECTOR_SIZE` | `EMBEDDING_VECTOR_SIZE` | `768` | Dimensionality of vectors in Qdrant collection. |

### 5. AI Confidence Formula & Worked Example

#### Formula
AI Confidence is calculated directly from the similarity scores of the knowledge base chunks retrieved for the incident:

$$\text{ai\_confidence} = \begin{cases} 0.0 & \text{if } \text{scores is empty} \\ \operatorname{clamp}\Big(\operatorname{round}\big(\max(\text{scores}), 4\big), 0.0, 1.0\Big) & \text{otherwise} \end{cases}$$

Confidence is strictly grounded in empirical retrieval quality—the AI never self-reports an ungrounded subjective confidence score.

#### Worked Example
1. **Incident**: User reports `"VPN client disconnects intermittently"`.
2. **Retrieval**: `searchKB("VPN client disconnects")` retrieves three matching chunks:
   - Chunk 1: `KB0010002` (score: `0.7250`)
   - Chunk 2: `KB0010002` (score: `0.8140`)
   - Chunk 3: `KB0010001` (score: `0.6500`)
3. **Score Set**: `S = [0.7250, 0.8140, 0.6500]`
4. **Computation**:
   - Best score = $\max(0.7250, 0.8140, 0.6500) = 0.8140$
   - Rounded to 4 decimal places = `0.8140`
   - Clamped between $0.0$ and $1.0$ = `0.8140`
5. **Output**: The payload sent to ServiceNow contains `"ai_confidence": 0.8140` alongside `"human_review_required": true`.

### 6. Offline Test Suite Execution

The test suite runs 100% offline without LLM API calls or live network connections using an in-memory Qdrant instance and a fake write-back port:

```bash
python -m pytest tests/test_tools.py -v
```