# Decisions and Limitations

## 1. Purpose

This document records the main architectural and operational decisions made in the AI ServiceNow Support Assistant, the reasoning behind those decisions, and the current limitations of the implementation.

The goal is to make the system easier to maintain and to explain why specific design choices were made.

---

# 2. Design Decisions

## 2.1 Return `202 Accepted` from the Webhook

### Decision

The webhook returns `202 Accepted` after the event has been authenticated, validated, recorded for idempotency, passed the initial guardrails, and queued for background processing.

It does not wait for:

* ServiceNow incident retrieval
* Knowledge-base retrieval
* LLM generation
* Agent execution
* ServiceNow write-back

### Why

AI processing can take significantly longer than a normal HTTP request because it includes network calls, vector retrieval, and LLM execution.

Keeping this work inside the webhook request would make the endpoint slower and less reliable.

The asynchronous design allows FastAPI to acknowledge the event quickly while Celery handles the longer processing workflow.

```text
ServiceNow
    |
    | POST /api/webhook
    v
FastAPI
    |
    | validate + persist + queue
    v
202 Accepted
    |
    v
Redis
    |
    v
Celery Worker
    |
    v
AI Processing
```

---

## 2.2 Use Redis + Celery to Decouple the Webhook from AI Processing

### Decision

The webhook places a minimal worker payload into a Redis-backed Celery queue instead of running the AI pipeline directly.

The queued payload contains identifiers such as:

```text
event_id
sys_id
number
received_at
```

The full incident description is not placed into the queue.

### Why

This separates two responsibilities:

* **FastAPI:** receive, authenticate, validate, persist, and enqueue.
* **Celery:** perform the long-running incident processing.

This also allows worker failures to be handled independently from the HTTP request.

The worker retrieves the latest incident from ServiceNow when processing begins, so the AI pipeline works with a fresh copy of the incident.

---

## 2.3 Use PostgreSQL for Idempotency and Processing State

### Decision

PostgreSQL stores processing state in dedicated tables:

* `events_log`
* `completed_events`
* `dead_letter_events`

The incident `sys_id` is used to prevent duplicate event processing.

### Why

ServiceNow or another upstream component may send the same event more than once.

Without idempotency:

```text
Same Incident
    |
    +----> Job 1
    |
    +----> Job 2
```

The AI could process the same incident twice and potentially create duplicate suggestions.

With the idempotency check:

```text
Same Incident
    |
    +----> First event → processed
    |
    +----> Duplicate → duplicate_ignored
```

The completion marker also allows the worker to distinguish an already completed incident from an unfinished one after redelivery.

---

## 2.4 Use Late Acknowledgement and Worker-Loss Redelivery

### Decision

Celery uses reliability settings including:

```text
task_acks_late = True
task_reject_on_worker_lost = True
worker_prefetch_multiplier = 1
```

### Why

The system must reduce the chance of losing an incident if a worker crashes during processing.

Late acknowledgement means the task is not acknowledged prematurely.

If the worker is lost before the task is safely completed, the task can be redelivered.

The prefetch value is limited so workers do not reserve a large number of tasks unnecessarily.

This is particularly important because incident processing contains multiple external operations and can take longer than a simple function call.

---

## 2.5 Fetch the Incident Again Inside the Worker

### Decision

The webhook does not send the complete incident text through the queue.

The Celery worker retrieves the current incident directly from ServiceNow before running the AI pipeline.

### Why

The webhook payload represents the event that triggered processing, while ServiceNow remains the source of truth for the current incident state.

Fetching the incident again means the worker can process the latest available record instead of relying on potentially stale queued text.

It also keeps the queue payload small.

---

## 2.6 Run Guardrails Before the Agent

### Decision

Incident input is passed through guardrails before reaching the ReAct agent.

The guardrails include:

* length limiting
* sensitive-value masking
* keyword/tag extraction
* prompt-injection detection
* wrapping incident content as untrusted data

The worker also performs guardrail processing after retrieving the fresh ServiceNow incident.

### Why

The incident description is external input and must not be treated as trusted instructions for the LLM.

The guardrails provide a security boundary before the model receives the incident content.

The second check is intentional: the worker retrieves a fresh copy of the incident, so that fresh data must also pass the same safety checks.

---

## 2.7 Use Qdrant for Knowledge Retrieval

### Decision

Knowledge-base content is embedded and stored in Qdrant for semantic retrieval.

The retrieval process:

```text
Incident/query
     |
     v
BGE embedding
     |
     v
Qdrant
     |
     v
Top-K chunks + similarity scores
```

Retrieval is restricted to published knowledge.

### Why

The agent needs relevant knowledge-base content rather than relying only on the LLM's general knowledge.

Filtering retrieval to published content also prevents draft or retired material from becoming the basis of an AI suggestion.

---

## 2.8 Require Grounding Before Suggesting a Resolution

### Decision

The agent cannot submit a suggestion unless the response is supported by retrieved knowledge-base content.

The validation checks that:

* relevant content was retrieved
* the response contains a numbered procedure
* each step has a citation
* cited article IDs were actually retrieved
* the response has valid sources

### Why

The main purpose of the agent is to assist with ServiceNow incidents using the organization's knowledge base.

If the KB does not contain sufficient evidence, the system escalates instead of inventing a resolution.

This makes escalation a normal outcome of insufficient knowledge rather than treating every incident as something the AI must answer.

---

## 2.9 Keep the Agent Limited to Four Tools

### Decision

The ReAct agent is registered with exactly four tools:

```text
searchKB
addworknote
suggestAnswer
requestHR
```

The agent has no tool for:

* resolving an incident
* closing an incident
* reassigning an incident

### Why

The AI should prepare and assist with incident resolution, not make the final operational decision.

The architecture therefore limits the agent's capabilities at the tool layer instead of relying only on instructions in the prompt.

---

## 2.10 Require Human Review

### Decision

Every AI suggestion sets:

```text
human_review_required = true
```

A ServiceNow fulfiller must approve, edit, or reject the suggestion before it becomes customer-facing communication.

### Why

The AI-generated response is treated as a draft.

The human reviewer remains responsible for deciding whether the suggested response is appropriate for the incident.

The system therefore separates:

```text
AI suggestion
      ↓
Human review
      ↓
Customer-facing response
```

The AI does not directly write its generated answer into customer-facing `comments`.

---

## 2.11 Keep AI Work Notes Separate from Customer Comments

### Decision

AI internal processing information is written to `work_notes`, while customer-facing communication uses `comments` through the human review process.

### Why

These fields have different audiences.

`work_notes` are intended for internal support/fulfillment information.

`comments` are customer-visible.

Keeping them separate prevents an internal AI processing message from accidentally becoming customer communication.

---

## 2.12 Stop After the First Write-back Failure

### Decision

If a ServiceNow write-back fails, the agent does not continue performing additional write-back operations.

Transient failures are retried with backoff. If the write-back still fails, the run stops.

### Why

Continuing after a failed write could create an inconsistent incident state.

For example:

```text
Write 1 → failed
Write 2 → attempted
Write 3 → attempted
```

could produce partial updates.

Stopping at the first write-back failure makes the failure explicit and avoids continuing a run whose ServiceNow state is uncertain.

---

# 3. Current Limitations

## 3.1 Confidence Is Based on Retrieval Similarity

The AI confidence value is derived from the highest retrieval similarity score and clamped to the valid `0–1` range.

It is therefore a retrieval-based confidence measure, not a calibrated probability that the generated answer is correct.

For example:

```text
confidence = highest retrieval score
```

A high similarity score does not mathematically guarantee that the generated resolution is correct.

---

## 3.2 Prompt-Injection Detection Can Produce False Positives

The guardrail system uses keyword/pattern-based detection for suspicious input.

Because this is rule-based detection, legitimate incident text can potentially contain words or phrases that look like prompt-injection instructions.

Therefore:

```text
Detected keyword
        ↓
Incident may be rejected
```

does not necessarily mean the incident is actually malicious.

This is a limitation of the current detection approach.

---

## 3.3 Incident Text Is Truncated Before Processing

The incident context has a configured maximum length.

This protects the system from excessively large inputs, but it also means that information beyond the configured limit may not reach the agent.

The system therefore trades completeness for bounded input size.

---

## 3.4 Sensitive-Value Masking Has Ordering Constraints

Sensitive information is masked before the incident is passed deeper into the AI pipeline.

Because truncation and masking are separate processing stages, the current implementation has an ordering limitation: information near the truncation boundary may not behave exactly the same as information inside the retained portion.

This should be considered when improving the sanitization pipeline.

---

## 3.5 The Current Compose Stack Does Not Run Qdrant as a Compose Service

The Docker Compose configuration includes the main application services such as:

```text
FastAPI
Celery
PostgreSQL
Redis
```

Qdrant is configured separately through its environment settings rather than being included as a Qdrant service in the current Compose stack.

Therefore, a clean-machine setup still requires the configured Qdrant environment to be available.

---

## 3.6 Knowledge Retrieval Depends on KB Coverage

The agent can only produce a grounded suggestion when the knowledge base contains sufficiently relevant information.

If no retrieved chunk reaches the configured threshold:

```text
score < 0.70
```

the agent escalates instead of generating an unsupported fix.

This means the quality of the AI suggestion is directly constrained by the coverage and quality of the indexed knowledge base.

---

## 3.7 The Current Idempotency Model Uses `sys_id`

The incident `sys_id` is used as the idempotency key.

This prevents the same incident from being processed repeatedly, but it also means that retention and lifecycle behavior of the stored event state must be managed carefully.

If the system eventually needs to support multiple intentional processing events for the same incident, the idempotency strategy would need to distinguish those events.

---

## 3.8 Worker Redelivery Does Not Mean the Task Is Always Safe to Repeat

Celery redelivery protects against worker loss, but external side effects still require idempotent handling.

The project addresses this with completion markers and by checking whether an event has already completed before continuing.

However, any future tool that performs additional external side effects should also be designed with idempotency in mind.

---

## 3.9 The System Depends on External Services

The complete processing path depends on several external components:

```text
ServiceNow
Redis
PostgreSQL
Qdrant
LiteLLM / LLM provider
```

Failure of one of these services can prevent or delay incident processing.

The project includes retries and dead-letter handling for selected failure classes, but it cannot make an unavailable external dependency available.

---

## 3.10 The AI Is Not an Autonomous Incident Resolver

The system intentionally does not provide tools for:

* resolving incidents
* closing incidents
* reassigning incidents

The AI produces a suggestion or escalation.

Human review remains part of the final incident workflow.

This is a deliberate architectural constraint rather than a missing feature.

---

# 4. Future Enhancements

Potential future improvements include:

* More robust prompt-injection detection with fewer false positives.
* A calibrated confidence model instead of using retrieval similarity directly.
* A more explicit and configurable idempotency retention policy.
* Better sanitization ordering around truncation and masking.
* Including Qdrant directly in the Docker Compose development stack.
* More comprehensive crash-redelivery testing under realistic worker failures.
* Additional monitoring and alerting around DLQ growth and external-service failures.
* Expanded retrieval evaluation against a larger benchmark set.

These are future improvements; they are not required for the current processing flow to enforce its existing safety and reliability boundaries.

---

# 5. Decision Summary

| Decision                      | Reason                                                            |
| ----------------------------- | ----------------------------------------------------------------- |
| `202 Accepted`                | Keep webhook fast and move long-running work to the background    |
| Redis + Celery                | Decouple event reception from AI processing                       |
| PostgreSQL state tables       | Idempotency, completion tracking, and DLQ persistence             |
| Late acknowledgements         | Reduce task loss after worker failure                             |
| Fresh ServiceNow GET          | Process the latest incident state                                 |
| Guardrails                    | Treat incident content as untrusted input                         |
| Qdrant retrieval              | Ground AI responses in organizational KB content                  |
| Grounding validation          | Prevent unsupported suggestions                                   |
| Four-tool agent               | Limit AI capabilities                                             |
| Human review                  | Keep final customer communication under human control             |
| Separate work notes/comments  | Keep internal AI information separate from customer communication |
| Stop after write-back failure | Avoid continuing an uncertain/partially written state             |

The overall design prioritizes asynchronous reliability, grounded AI output, limited AI permissions, and human control over customer-facing incident responses.
