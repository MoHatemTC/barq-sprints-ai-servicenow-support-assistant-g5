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

| File                                 | Role                                                                    |
| ------------------------------------ | ----------------------------------------------------------------------- |
| `src/agent/react_agent.py`           | The loop, guardrails, `AgentConfig`, `AgentResult`, `AgentFailure`      |
| `src/agent/prompts/system_prompt.py` | Versioned system prompt (`PROMPT_VERSION`, changelog)                   |
| `src/agent/run_context.py`           | Per-run state: retrieved articles, scores, searches, outcome, event log |
| `agent/agent.py`                     | Task 5 retriever (`KnowledgeRetriever`) used by `searchKB`              |
| `run_pipeline.py`                    | `process_incident()`, called by the webhook background task             |
| `tests/test_agent_loop.py`           | Offline agent-loop tests                                                |
| `Scripts/try_agent.py`               | One real run, printing the full transcript                              |
| `Scripts/make_evidence.py`           | Regenerates `docs/evidence/*.md` from real runs                         |

### Entry point and result

```python
from src.agent.react_agent import run_agent

result = run_agent(sys_id, incident, tools, ctx=run_ctx)

result.status
result.terminal_tool
result.iterations
result.steps
```

`AgentResult` also carries `procedure`, `sources`, `reason`, `searches`, `grounding_rejections`, `fallback_reason`, `total_tokens`, `max_score`, `retrieved_chunks`, and `prompt_version`.

Unrecoverable LLM failures raise `AgentFailure`, which the pipeline turns into an escalation.

### Tools

| Tool                                | Terminal | Purpose                                                   |
| ----------------------------------- | -------- | --------------------------------------------------------- |
| `searchKB(query)`                   | No       | Dense search over published KB chunks                     |
| `addworknote(note)`                 | No       | Internal note                                             |
| `suggestAnswer(procedure, sources)` | Yes      | Submit a grounded, numbered, cited fix for human approval |
| `requestHR(reason)`                 | Yes      | Hand the incident to a human                              |

No tool can resolve, close, or reassign an incident. That boundary is structural.

### Guardrails

| Guardrail              | Rule                                          | When broken        |
| ---------------------- | --------------------------------------------- | ------------------ |
| Guaranteed termination | Max iterations, time budget, and token budget | Forced `requestHR` |
| Search cap             | Max `AGENT_MAX_                               |                    |
