# ServiceNow Setup Guide

## 1. Overview

This document describes the ServiceNow-side configuration required for the **AI ServiceNow Support Assistant**.

The ServiceNow configuration provides:

* The custom scoped application.
* AI-related incident fields.
* Integration access.
* Incident webhook configuration.
* Knowledge-base event integration.
* AI write-back.
* Human review actions.
* Lifecycle protection.

The overall integration is:

```text
ServiceNow
    │
    ├── Incident
    │      │
    │      ▼
    │   Business Rule
    │      │
    │      ▼
    │   Signed Webhook
    │      │
    │      ▼
    │   FastAPI
    │
    ├── Knowledge Base
    │      │
    │      ▼
    │   KB Event
    │      │
    │      ▼
    │   FastAPI
    │
    └── AI Write-back
           │
           ▼
      Human Review
```

---

# 2. Custom Scoped Application

The ServiceNow configuration uses a custom scoped application for the project.

The application contains the project-specific configuration required to integrate the AI assistant with ServiceNow incidents and the knowledge base.

The custom incident fields use the project scope prefix:

```text
x_2216229_sprint_1_
```

These fields are used to store AI processing state and review information.

---

# 3. Custom AI Incident Fields

The AI assistant uses custom fields on the ServiceNow Incident record.

The main fields are:

| Field                                      | Purpose                                    |
| ------------------------------------------ | ------------------------------------------ |
| `x_2216229_sprint_1_ai_status`             | Stores the current AI processing status    |
| `x_2216229_sprint_1_ai_confidence`         | Stores the AI confidence value             |
| `x_2216229_sprint_1_ai_suggested_response` | Stores the AI-generated suggested response |
| `x_2216229_sprint_1_human_review_required` | Indicates that human review is required    |
| `x_2216229_sprint_1_ai_processed`          | Indicates that AI processing has occurred  |

The project also uses the standard ServiceNow `work_notes` field for internal AI processing notes.

---

# 4. AI Status

The AI status field represents the result of the AI processing workflow.

A suggestion can result in an AI status such as:

```text
suggested
```

An escalation can result in:

```text
escalated
```

The status is written by the AI integration through the controlled write-back layer.

The AI does not use this field to directly control the normal ServiceNow incident lifecycle.

---

# 5. Integration User

A dedicated ServiceNow integration user should be used for communication between the ServiceNow instance and the AI backend.

The integration account is responsible for the API operations required by the project.

Its permissions should be limited to the operations required by the integration.

The integration credentials must not be stored in source code.

They are provided through environment variables on the backend.

The backend configuration includes:

```text
SERVICENOW_USERNAME
SERVICENOW_PASSWORD
```

---

# 6. Incident Webhook

The incident integration sends incident events to:

```text
POST /api/webhook
```

The request is authenticated using an HMAC-SHA256 signature.

The ServiceNow request includes:

```text
X-ServiceNow-Signature
```

The backend verifies this signature using:

```text
WEBHOOK_SECRET
```

The ServiceNow-side secret and backend secret must correspond.

---

# 7. Incident Webhook Payload

The incident webhook sends the required incident information.

The payload structure is:

```json
{
  "sys_id": "0123456789abcdef0123456789abcdef",
  "number": "INC0010001",
  "short_description": "VPN connection problem",
  "description": "The user cannot connect to the company VPN."
}
```

The backend validates the payload before queueing the incident.

The main fields are:

| Field               | Description                           |
| ------------------- | ------------------------------------- |
| `sys_id`            | Unique ServiceNow incident identifier |
| `number`            | Incident number                       |
| `short_description` | Short incident description            |
| `description`       | Full incident description             |

---

# 8. Business Rule for Incident Events

A ServiceNow Business Rule is responsible for triggering the incident integration.

The Business Rule sends the required incident information to the backend through the configured outbound integration.

The high-level flow is:

```text
Incident Event
     │
     ▼
Business Rule
     │
     ▼
Build Payload
     │
     ▼
Generate Signature
     │
     ▼
HTTP Request
     │
     ▼
FastAPI /api/webhook
```

The Business Rule should only send the information required by the webhook contract.

---

# 9. Webhook Authentication

The webhook must not be treated as an unauthenticated HTTP endpoint.

The request contains:

```text
X-ServiceNow-Signature
```

The backend calculates and verifies the expected HMAC-SHA256 signature using the shared secret.

The verification flow is:

```text
ServiceNow
    │
    │ Request Body
    │
    ├── HMAC-SHA256 + Secret
    │
    ▼
Signature
    │
    ▼
FastAPI
    │
    ├── Calculate expected signature
    │
    └── Compare signatures
            │
       ┌────┴────┐
       ▼         ▼
     Valid     Invalid
       │         │
       ▼         ▼
   Continue     Reject
```

A missing or invalid signature is rejected by the backend.

---

# 10. Knowledge Base Integration

The ServiceNow knowledge base is the source of the support knowledge used by the AI agent.

The backend retrieves published KB articles and indexes them into Qdrant.

The ServiceNow KB integration uses the configured:

```text
SERVICENOW_KB_ID
SERVICENOW_KB_CATEGORY_ID
```

The backend retrieves published knowledge content and processes it through the KB ingestion pipeline.

---

# 11. Knowledge Base Events

The project also provides a KB event endpoint:

```text
POST /articles/events
```

This endpoint is used to notify the backend when a KB article changes.

The supported operations include:

```text
insert
update
delete
retire
```

The request is protected using the configured API secret.

The expected authentication header is:

```text
X-API-Key
```

The backend compares it with:

```text
API_SECRET_KEY
```

---

# 12. KB Event Flow

The KB event architecture is:

```text
ServiceNow KB Article
        │
        ▼
Business Rule
        │
        ▼
KB Event
        │
        ▼
POST /articles/events
        │
        ▼
FastAPI
        │
        ▼
KB Ingestion Service
        │
        ▼
Qdrant
```

This allows KB changes to be communicated to the backend so the vector index can remain synchronized with the ServiceNow knowledge base.

---

# 13. REST Messages

ServiceNow outbound HTTP communication is configured through the appropriate ServiceNow REST integration mechanisms.

The integration is used to communicate with the FastAPI backend for:

* Incident webhook events.
* Knowledge-base events.

The outbound requests must include the authentication information required by the corresponding backend endpoint.

For the incident webhook:

```text
X-ServiceNow-Signature
```

For KB events:

```text
X-API-Key
```

---

# 14. AI Write-back

After the AI agent completes its processing, the backend communicates with the ServiceNow Incident Table API.

The write-back layer is intentionally restricted to an allow-list of AI-controlled fields.

The allowed AI fields include:

```text
x_2216229_sprint_1_ai_status
x_2216229_sprint_1_ai_confidence
x_2216229_sprint_1_ai_suggested_response
x_2216229_sprint_1_human_review_required
x_2216229_sprint_1_ai_processed
work_notes
```

The `comments` field is intentionally excluded from direct AI write-back.

This keeps customer-facing communication under human control.

---

# 15. Protected Incident Fields

The AI write-back client does not control the normal incident lifecycle fields.

The following fields are excluded from AI write-back:

```text
state
assigned_to
assignment_group
close_code
close_notes
```

This prevents the AI from directly resolving, closing, assigning, or reassigning incidents.

---

# 16. Suggestion Write-back

When the agent successfully generates a grounded response, the backend writes the suggestion to ServiceNow.

The resulting state includes:

```text
ai_status = suggested
ai_suggested_response = <generated response>
human_review_required = true
ai_processed = true
```

The confidence value is also stored.

The suggestion remains subject to human review.

---

# 17. Escalation Write-back

When the agent cannot safely generate a grounded response, it can request human escalation.

The write-back records an escalation state.

The resulting state includes:

```text
ai_status = escalated
ai_suggested_response = empty
human_review_required = true
ai_processed = true
```

The escalation reason can be recorded as an internal work note.

---

# 18. Human Review

The ServiceNow side provides a human review workflow for AI-generated suggestions.

The reviewer can choose:

```text
Approve
Edit
Reject
```

The workflow is:

```text
AI Suggestion
      │
      ▼
Human Review
      │
 ┌────┼────┐
 ▼    ▼    ▼
Approve Edit Reject
 │      │      │
 ▼      ▼      ▼
Customer   Customer  Escalation
Response   Response
```

The AI does not automatically send the suggested response to the customer.

---

# 19. Approve Action

When the reviewer approves the AI suggestion:

1. The suggested response is copied to the customer-facing `comments` field.
2. Internal AI information is not exposed as customer communication.
3. Human review is cleared according to the configured ServiceNow workflow.

The approval is therefore a human-controlled transition from:

```text
AI suggestion
      ↓
Human approval
      ↓
Customer-facing response
```

---

# 20. Edit Action

The Edit action allows the fulfiller to modify the AI-generated suggestion before using it as customer-facing communication.

The flow is:

```text
AI Suggestion
      ↓
Human edits response
      ↓
Final human-approved response
      ↓
comments
```

This allows the human fulfiller to correct or improve the AI suggestion before it reaches the customer.

---

# 21. Reject Action

The Reject action prevents the AI suggestion from being used as the customer-facing response.

The incident remains in the human-controlled escalation flow.

The rejection can also result in an internal work note describing the AI escalation.

---

# 22. UI Policy

The ServiceNow UI configuration is used to control the visibility and editability of the AI-related fields during the review workflow.

The goal is to make AI-generated information visible to the fulfiller while keeping the AI-controlled state separate from normal incident lifecycle fields.

The AI fields are therefore treated as integration-controlled information rather than replacements for standard ServiceNow incident fields.

---

# 23. Lifecycle Guard

The project includes a lifecycle guard to prevent AI-generated work notes from incorrectly clearing the human-review state.

The lifecycle guard distinguishes between:

```text
AI-generated activity
```

and:

```text
Human activity
```

The human-review state is cleared only under the configured human-review conditions, such as a human work note or appropriate incident lifecycle transitions.

AI-generated notes do not themselves count as human review.

---

# 24. End-to-End ServiceNow Flow

The complete ServiceNow integration can be summarized as:

```text
                    ServiceNow
                        │
             ┌──────────┴──────────┐
             │                     │
             ▼                     ▼
        Incident               KB Article
             │                     │
             ▼                     ▼
      Business Rule          Business Rule
             │                     │
             ▼                     ▼
      Signed Webhook             KB Event
             │                     │
             ▼                     ▼
       POST /api/webhook   POST /articles/events
             │                     │
             └──────────┬──────────┘
                        ▼
                    FastAPI
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
        Incident Agent       KB Ingestion
              │                   │
              ▼                   ▼
        AI Processing          Qdrant
              │
              ▼
       ServiceNow Write-back
              │
              ▼
        Human Review
              │
       ┌──────┼──────┐
       ▼      ▼      ▼
    Approve  Edit   Reject
       │      │      │
       └──────┴──────┘
              │
              ▼
     Human-controlled outcome
```

---

# 25. ServiceNow Configuration Checklist

Before testing the complete integration, verify:

* [ ] Custom scoped application exists.
* [ ] AI incident fields exist.
* [ ] Integration user exists.
* [ ] Required roles/permissions are assigned.
* [ ] Incident Business Rule is configured.
* [ ] Incident outbound integration is configured.
* [ ] HMAC secret matches the backend `WEBHOOK_SECRET`.
* [ ] KB configuration is available.
* [ ] KB event Business Rule is configured.
* [ ] KB event authentication uses `X-API-Key`.
* [ ] `API_SECRET_KEY` matches the configured ServiceNow value.
* [ ] AI write-back fields are available.
* [ ] Protected incident lifecycle fields are not controlled by the AI.
* [ ] Human review actions are configured.
* [ ] UI policy is active.
* [ ] Lifecycle guard is active.

---

# 26. Security Checklist

Never place credentials directly inside scripts committed to Git.

Verify that:

```text
ServiceNow credentials
        ↓
Environment variables / secure configuration
```

and:

```text
Webhook secret
        ↓
Secure configuration
        ↓
HMAC signature verification
```

are used instead of hard-coded secrets.

The ServiceNow integration should also use the minimum permissions required for the configured operations.

---

# 27. Final ServiceNow Architecture

The ServiceNow-side responsibilities are intentionally separated:

| Responsibility           | ServiceNow Component   |
| ------------------------ | ---------------------- |
| Incident event detection | Business Rule          |
| Webhook communication    | REST integration       |
| Webhook authentication   | HMAC signature         |
| KB event detection       | Business Rule          |
| KB event authentication  | API key                |
| AI result storage        | Custom Incident fields |
| Internal AI information  | `work_notes`           |
| Customer communication   | `comments`             |
| AI approval              | Human reviewer         |
| AI editing               | Human reviewer         |
| AI rejection             | Human reviewer         |
| Lifecycle protection     | Lifecycle Guard        |

The ServiceNow configuration therefore acts as the system of record, event source, AI result destination, and human-review interface, while the AI backend performs asynchronous processing and knowledge-grounded reasoning.
