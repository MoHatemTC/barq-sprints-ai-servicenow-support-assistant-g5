# Troubleshooting

This guide covers common runtime and operational failures in the AI ServiceNow Support Assistant. Each issue is described by its observable symptom, probable root cause, and concrete resolution.

---

## 1. Webhook Returns `401 Unauthorized`

### Symptom

ServiceNow sends an incident webhook, but the FastAPI endpoint returns:

```text
401 Unauthorized
```

The incident is not recorded in `events_log` and is not queued for Celery processing.

### Probable Root Cause

The `X-ServiceNow-Signature` header is missing or the provided HMAC-SHA256 signature does not match the request body.

The webhook authentication uses the raw request body and `WEBHOOK_SECRET`.

### Resolution

1. Verify that ServiceNow sends the `X-ServiceNow-Signature` header.
2. Verify that `WEBHOOK_SECRET` is configured in the backend environment.
3. Make sure ServiceNow signs the exact request body being sent.
4. Check the backend logs for the signature validation result.
5. Retry the webhook after correcting the secret or signature generation.

Do not disable signature verification to bypass the problem.

---

## 2. Webhook Returns `duplicate_ignored`

### Symptom

A webhook request is accepted, but the response indicates:

```json
{
  "status": "duplicate_ignored"
}
```

No second Celery job is created.

### Probable Root Cause

The same ServiceNow `sys_id` has already been recorded in `events_log`.

The database uses the incident `sys_id` to enforce idempotency, preventing the same incident event from creating duplicate processing jobs.

### Resolution

1. Check `events_log` for the incident `sys_id`.
2. Confirm whether the incident has already been accepted for processing.
3. Check the corresponding worker logs and completion state.
4. If the original processing failed permanently, inspect `dead_letter_events`.
5. Do not manually create a second event unless replaying the incident is an intentional operational action.

This behavior prevents duplicate AI processing and duplicate suggestions.

---

## 3. ServiceNow Incident Fetch Fails with `429`, `5xx`, or Timeout

### Symptom

The webhook is accepted, but the Celery worker cannot retrieve the latest incident from ServiceNow.

Typical failures include:

```text
429 Too Many Requests
500 Internal Server Error
502 Bad Gateway
503 Service Unavailable
504 Gateway Timeout
Network timeout / connection failure
```

### Probable Root Cause

The ServiceNow Table API is temporarily unavailable, rate-limited, or unreachable from the worker.

### Resolution

The worker treats network errors, `429`, and `5xx` responses as retryable failures.

It retries the operation up to the configured maximum:

```text
Attempt 1
   ↓
Retry
   ↓
Attempt 2
   ↓
Retry
   ↓
Retry limit reached
   ↓
Dead Letter Queue
```

The retries use exponential backoff with jitter.

After retry exhaustion:

1. Inspect the Celery worker logs.
2. Check ServiceNow availability and rate limits.
3. Verify `SERVICENOW_URL` and authentication credentials.
4. Check network connectivity from the worker container.
5. Inspect the corresponding dead-letter record.

The incident is not sent to the agent until the worker successfully retrieves the fresh ServiceNow record.

---

## 4. ServiceNow Incident Fetch Returns a Permanent `4xx` Error

### Symptom

The worker receives a client error such as:

```text
404 Not Found
```

The task does not continue retrying indefinitely.

### Probable Root Cause

The requested incident is invalid, unavailable, or the integration request is not authorized.

Unlike temporary `429` and `5xx` failures, these errors are classified as permanent failures.

### Resolution

1. Verify that the incident still exists in ServiceNow.
2. Verify the ServiceNow `sys_id`.
3. Check the integration user's permissions.
4. Verify the requested ServiceNow endpoint and table.
5. Inspect the dead-letter record for the failure details.

A permanent `4xx` failure is sent to the dead-letter path immediately rather than repeatedly retrying an error that is unlikely to succeed.

---

## 5. Incident Is Flagged as Malicious

### Symptom

The webhook is received, but the incident is not queued for the AI worker.

The event is marked:

```text
flagged_malicious
```

and the webhook response indicates rejection.

### Probable Root Cause

The incident guardrails detected a suspicious prompt-injection or unsafe keyword pattern.

The system treats ServiceNow incident text as untrusted input and performs security checks before sending the event to the AI pipeline.

### Resolution

1. Inspect the incident text for prompt-injection patterns or suspicious instructions.
2. Confirm that the incident is a legitimate support request.
3. If the detection is a false positive, review the guardrail rule responsible for the match.
4. Do not bypass the guardrails simply to force the incident through the agent.
5. Re-submit the incident only after the input has been validated as safe.

Unsafe incidents are intentionally prevented from reaching the ReAct agent.

---

## 6. No Knowledge Base Result Meets the Score Threshold

### Symptom

The agent searches the knowledge base but no retrieved result reaches the configured similarity threshold:

```text
SCORE_THRESHOLD = 0.70
```

The agent does not generate a customer-facing fix.

### Probable Root Cause

The available published knowledge-base articles do not provide sufficiently relevant information for the incident.

### Resolution

The agent uses the `requestHR` tool instead of inventing a solution.

The resulting write-back marks the incident as:

```text
ai_status = escalated
human_review_required = true
```

The support team can then investigate the incident manually.

If this occurs unexpectedly:

1. Verify that the relevant KB article is published.
2. Verify that the article was successfully ingested into Qdrant.
3. Check the article's chunks and embeddings.
4. Verify the Qdrant collection.
5. Re-run KB ingestion if the article was recently created or updated.

The system should not lower the threshold simply to force an unsupported answer.

---

## 7. `suggestAnswer` Is Rejected Because the Citation Was Not Retrieved

### Symptom

The agent produces a proposed answer that references a knowledge-base article or information that was not actually retrieved during the current run.

The suggestion is rejected instead of being written back as a valid AI answer.

### Probable Root Cause

The grounding validation detected that the generated response is not fully supported by the retrieved KB context.

The agent is required to base its suggested resolution only on retrieved knowledge.

### Resolution

The agent can continue within its configured limits by performing another KB search and attempting to ground the response.

The relevant limits include:

```text
Maximum iterations       = 6
Maximum KB searches      = 3
Maximum grounding rejects = 2
```

If grounding continues to fail, the agent uses `requestHR` and escalates the incident rather than producing an unsupported answer.

---

## 8. LLM or Agent Execution Fails

### Symptom

The worker successfully retrieves the incident, but the AI pipeline cannot complete because the LLM or agent execution fails.

### Probable Root Cause

Possible causes include:

* LLM service unavailable.
* LiteLLM connection failure.
* LLM timeout.
* Agent execution failure.
* Unexpected exception during the ReAct loop.

### Resolution

1. Check the LLM/LiteLLM service availability.
2. Verify the configured LLM URL and API key.
3. Check the worker logs for timeout or connection errors.
4. Verify the configured model.
5. Check the agent execution trace and metrics.

The pipeline catches `AgentFailure` and creates an escalation result rather than allowing the worker service to crash.

The AI should not generate an unsupported fallback answer when the model is unavailable.

---

## 9. ServiceNow Write-back Fails

### Symptom

The agent reaches a terminal action such as `suggestAnswer` or `requestHR`, but the ServiceNow PATCH operation fails.

### Probable Root Cause

The ServiceNow Table API may be unavailable, rate-limiting the request, rejecting authentication, or returning another HTTP error.

Transient failures include:

```text
429
500
502
503
504
```

Network failures are also treated as transient.

### Resolution

The write-back client retries transient failures using exponential backoff:

```text
1 second
   ↓
2 seconds
   ↓
4 seconds
```

If the write-back still fails, processing stops at the first write-back failure.

The local pipeline records the result as an escalation/failure state rather than continuing to perform additional write-back operations.

Check:

1. ServiceNow availability.
2. Integration credentials.
3. Incident `sys_id`.
4. Allow-listed custom fields.
5. Worker logs and retry attempts.

---

## 10. Celery Worker Crashes During Incident Processing

### Symptom

A worker process crashes or is killed while processing an incident.

### Probable Root Cause

The worker may have experienced a process crash, container failure, out-of-memory condition, or another unexpected termination.

### Resolution

The Celery reliability configuration is designed to support redelivery:

```text
task_acks_late = True
task_reject_on_worker_lost = True
worker_prefetch_multiplier = 1
```

With late acknowledgement, the task is acknowledged only after processing reaches the appropriate completion point.

If the worker is lost before acknowledgement, the message can be redelivered.

The completion marker is also checked before processing so a successfully completed incident is not processed again unnecessarily.

Operational checks:

1. Inspect the worker container logs.
2. Check whether the worker process was restarted.
3. Check the task state.
4. Verify whether the incident appears in `completed_events`.
5. If it was not completed, allow the message to be redelivered.

---

## 11. Celery Worker Does Not Start

### Symptom

The FastAPI service starts, but the Celery worker fails to start or cannot connect to the broker.

### Probable Root Cause

The Redis configuration is missing or incorrect.

The worker requires:

```text
REDIS_URL
```

and uses Redis as both the Celery broker and backend.

### Resolution

1. Verify that Redis is running.
2. Verify the `REDIS_URL` environment variable.
3. When running with Docker Compose, make sure the URL uses the Compose service name:

```text
redis://redis:6379/0
```

4. Check that the worker container can reach the Redis container.
5. Restart the worker after correcting the configuration.

---

## 12. Qdrant Collection Is Missing or Empty

### Symptom

The application starts, but KB searches return no useful results or Qdrant reports that the expected collection does not exist.

### Probable Root Cause

The Qdrant collection has not been created or the knowledge base has not been indexed.

The project uses the configured KB collection for vector retrieval.

### Resolution

1. Verify Qdrant connectivity.
2. Verify the Qdrant URL and credentials.
3. Check whether the expected collection exists.
4. Run the project's KB reindex/ingestion process.
5. Verify that published KB articles were embedded and upserted.
6. Retry the incident after confirming that the collection contains vectors.

---

## Failure Handling Summary

| Failure                           | System Behavior                                 | Operational Action          |
| --------------------------------- | ----------------------------------------------- | --------------------------- |
| Missing/invalid webhook signature | `401`, request rejected                         | Check HMAC secret/signature |
| Duplicate `sys_id`                | `duplicate_ignored`                             | Inspect existing event      |
| Injection detected                | `flagged_malicious`, not queued                 | Review incident content     |
| ServiceNow `429`/`5xx`/timeout    | Retry with backoff, then DLQ                    | Check ServiceNow/network    |
| ServiceNow permanent `4xx`        | Immediate DLQ                                   | Check incident/permissions  |
| No KB score ≥ `0.70`              | `requestHR` → escalation                        | Check KB coverage           |
| Citation not grounded             | Suggestion rejected; retry/search within limits | Check retrieved context     |
| LLM failure                       | Escalation result                               | Check LLM/LiteLLM           |
| Write-back failure                | Stop at first failure                           | Check ServiceNow PATCH      |
| Worker crash                      | Message can be redelivered                      | Check worker/task state     |
| Redis unavailable                 | Worker cannot process tasks                     | Check Redis/configuration   |
| Qdrant empty/missing              | KB retrieval fails                              | Reindex KB                  |

## General Diagnostic Order

When an incident appears not to have been processed, troubleshoot in this order:

```text
1. ServiceNow webhook
        ↓
2. HMAC authentication
        ↓
3. events_log / idempotency
        ↓
4. Redis
        ↓
5. Celery worker
        ↓
6. Fresh ServiceNow GET
        ↓
7. Guardrails
        ↓
8. ReAct agent
        ↓
9. Qdrant / KB retrieval
        ↓
10. ServiceNow write-back
        ↓
11. completed_events / dead_letter_events
```

This order follows the actual asynchronous processing path and helps isolate the failing component without skipping earlier stages.
