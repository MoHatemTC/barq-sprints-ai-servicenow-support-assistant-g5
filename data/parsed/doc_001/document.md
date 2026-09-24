<!-- page: 1 -->




> [Diagram p.1]
Sprints



S M A R T O P S   P R O G R A M M E

Project Knowledge Base

AI-Powered ServiceNow IT Incident Resolution Assistant - architecture, contracts, worked examples and the shared benchmark corpus


| DOCUMENT TYPE       | Knowledge base · shared reference and ingestible corpus                                                                  |
|---------------------|--------------------------------------------------------------------------------------------------------------------------|
| CLIENT / PARTNER    | BARQ Systems                                                                                                             |
| DELIVERED BY        | Sprints (sprints.ai)                                                                                                     |
| PROGRAMME           | AI Engineering -Agentic AI&RAGonITSM                                                                                     |
| APPLIES TO          | AI ServiceNow Support Assistant (intermediate) and Agentic Incident Resolution Platform (advanced)                       |
| AUDIENCE            | Interns, mentors and reviewers · both project levels                                                                     |
| COMPANION DOCUMENTS | The two Product Requirements Documents, which remain the contract. Where this document and a PRD disagree, the PRD wins. |
| VERSION             | 1.0 · September 2026                                                                                                     |


The one rule

The agent suggests. A human decides. No registered tool may resolve, close or reassign an incident, and no highrisk action reaches ServiceNow without a recorded human approval. This is a structural constraint, not a line in a prompt.

Prepared by Sprints for BARQ Systems.

<!-- page: 2 -->

Contents

If page numbers show as placeholders, open in Word and press Ctrl+A then F9 to update the field.

<!-- page: 3 -->

How to use this knowledge base

This document is the shared ground truth for the Sprints × BARQ Systems AI Engineering internship. Every team, at both levels, builds against what is written here.

Two Product Requirements Documents define what each level must deliver: the AI ServiceNow Support Assistant at intermediate level and the Agentic Incident Resolution Platform at advanced level. Those documents are contracts. They tell you what will be accepted at Demo Day, and they deliberately do not tell you how to build it.

This knowledge base is the other half. It carries the shared vocabulary, the data model, the exact payload contracts, the reference knowledge corpus, worked end-to-end examples and the benchmark set. Where a PRD says the retrieval tool shall return the top-k chunks with their similarity scores , this document shows you the JSON that comes back, the configuration that produced it, and the three ways teams usually get it wrong.

It is also a corpus

The system you are building retrieves knowledge articles and answers grounded questions over them. This document is written so it can be ingested by that same system. Every section carries a stable identifier such as KB-14 ; every reference article in Appendix A carries a machine-readable metadata block. Appendix C specifies exactly how to chunk and index this file. Point your ingestion pipeline at it and your agent can answer questions about its own architecture - which is a genuinely useful first smoke test of the pipeline you just wrote.

Read it in this order


| WHO                   | READ FIRST                                                                 | THEN                                                                            |
|-----------------------|----------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| Every intern, Week 0  | Parts 1 and 2 -orientation and the ServiceNow platform layer.              | Appendix A. Load the reference corpus into your instance before Sprint 1 ends.  |
| Intermediate teams    | Parts 3, 4 and 5, skipping anything marked advanced only .                 | Use cases UC-01, UC-02, UC-03, UC-07 and UC-08 in Part 6.                       |
| Advanced teams        | All of Parts 3 to 5, including the guardrail and state-machine sections.   | All eight use cases in Part 6, plus the evaluation contract in Part 7.          |
| Mentors and reviewers | Part 7 -the benchmark set, the metric definitions and the trace checklist. | Part 8 for the troubleshooting table you will be asked the same questions from. |


One rule that outranks everything else in this document

The agent suggests. A human decides. At intermediate level no registered tool can resolve, close or reassign an incident. At advanced level a high-risk action reaches ServiceNow only after a recorded human approval. This is a structural constraint, not a line in a prompt. If your only defence against a bad write is a sentence telling the model not to do it, you have not built the constraint.

<!-- page: 4 -->

Conventions used here

Section IDs. KB-01 to KB-32 and UC-01 to UC-08 . Cite them in stand-ups, pull requests and Demo Day. They are stable; they will not be renumbered.

Level tags. Content marked Intermediate applies to the AI ServiceNow Support Assistant only. Content marked Advanced applies to the Agentic Incident Resolution Platform only. Untagged content applies to both.

Field names. ServiceNow field labels appear in Title Case (AI Suggested Response); the underlying column names appear in code style ( u_ai_suggested_response ). Both are given the first time each field appears.

Placeholder values. Anything shown as <like_this> is yours to fill in. Anything shown as a literal value is part of the contract and must match.

<!-- page: 5 -->

Part 1 · Orientation

What you are actually building KB-01

A service desk receives an incident: 'I cannot connect to the VPN since my password reset.' A Tier-1 agent opens it, reads it, and then starts searching. They search the knowledge base. They search closed incidents. Somewhere in that platform is an article that solves this exact problem, written eighteen months ago by someone who has since left. The agent may find it in ninety seconds or in nine minutes, and the difference is not skill - it is luck about the words they happened to type.

That is the problem. It is not a modelling problem and it is not an automation problem. It is a retrieval problem wearing an ITSM costume. The knowledge exists, is written down, is correct, and is unreachable at the moment of failure because it can only be reached by keyword.

So you are building a system that, the instant an eligible incident is created, retrieves the knowledge articles that actually bear on the reported symptom, drafts a resolution grounded in those articles, cites them, and writes the draft back onto the incident form for a human to approve, edit or reject. Nothing more. Both project levels solve exactly that.

The system, end to end

One event in, one grounded suggestion out. Nothing polls; nothing auto-resolves.




> [Diagram p.5]
### 1 - SERVICENOW PLATFORM

> * **Incident raised**
>   * A requester reports a symptom. Category, service and text captured.
>   * **↓**
> * **Business Rule**
>   * Fires on insert and on relevant update. Checks eligibility.
>   * **↓**
> * **RESTMessageV2**
>   * Posts event_id, sys_id, number, event_type. Never the record.
>   * **↓** *(minimal event over HTTPS)*
> * **Incident form**
>   * AI Suggested Response and Human Review Required render here.
>   * *(Receives `write-back` from Section 3: Write back)*

---

### 2 - INGESTION EDGE — THE WEBHOOK IS THE FRONT DOOR

> *(Triggers from Section 1: RESTMessageV2 via `minimal event over HTTPS`)*
>
> * **POST /events**
>   * Authenticate the caller. Validate with Pydantic. 401 / 422 on failure.
>   * **↓**
> * **Idempotency + claim**
>   * Persist the event key. A replay is discarded. Claim the incident.
>   * **↓**
> * **202 Accepted**
>   * Returned before any model runs. ServiceNow is never blocked.
>   * **↓**
> * **Dispatch**
>   * Intermediate: background task. Advanced: Redis and Celery.
>   * **↓** *(dispatched to the worker)*

---

### 3 - REASONING — RETRIEVE, GROUND, DECIDE

> *(Triggers from Section 2: Dispatch via `dispatched to the worker`)*
>
> * **Retrieve**
>   * Qdrant. Dense top-k at intermediate; hybrid and rerank at advanced.
>   * **↓**
> * **Reason**
>   * LangChain agent, or an explicit LangGraph state machine.
>   * **↓**
> * **Ground + check**
>   * Numbered procedure, cited article. Score, risk and confidence gates.
>   * **↓**
> * **Write back**
>   * Table API: suggestion, confidence, work note, Human Review Required.
>   * **↓** *(write-back ➔ sends output to Section 1: Incident form)*

---

### 4 · Evidence — every run leaves a record

* **Langfuse holds the trace:** retrieval, generation, prompt version, tokens, latency, cost, errors.
* **PostgreSQL (advanced) holds:** executions, idempotency keys, approvals, failures and retry state.
* **Benchmark harness:** re-scores the same ten incidents after every change, so quality is measured, not claimed.



<!-- page: 6 -->

What it is not

It is not a chatbot. Nobody converses with it. It reacts to an event and produces one artefact.

It is not an auto-resolver. It never closes a ticket. It never emails a requester. It writes a suggestion into a field and raises a flag.

It is not a general-purpose assistant. It answers from the corpus you indexed, or it says it cannot and hands off.

It is not a demo of a framework. LangChain, LangGraph and Qdrant are means. Nobody at Demo Day will be impressed that you used them; they will ask what your top-3 hit rate was and how you measured it.

The two levels, and why they differ KB-02

Both levels attack the same business problem with the same event-driven trigger. The difference is engineering maturity , not the amount of AI. The advanced project is not 'the intermediate one plus more models'. It is the same idea built so it can be operated: durable queues, checkpointed state, permission classes, human approval as a first-class flow, guardrails against adversarial input, and evaluation wired into continuous integration so a regression fails a build rather than a customer.

Two levels, one business problem

The difference is engineering maturity, not the amount of Al.




> [Diagram p.6]
| | **Intermediate**<br>AI ServiceNow Support Assistant | **Advanced**<br>Agentic Incident Resolution Platform |
| :--- | :--- | :--- |
| **Trigger** | Business Rule, then RESTMessageV2 | Business Rule, then RESTMessageV2 |
| **Execution** | FastAPI background task | Redis queue + Celery workers |
| **Orchestration** | LangChain agent, four tools | LangGraph, checkpointed nodes |
| **Retrieval** | Dense top-k + metadata filters | Hybrid dense + sparse, reranked |
| **State** | Idempotency store only | PostgreSQL: state, approvals, audit |
| **Identity** | Least-privilege integration user | OAuth, least-privilege, ACL-governed |
| **Safety** | Restricted toolset, human review | Permission classes, interrupts, guardrails |
| **Evidence** | Langfuse traces + benchmark | Per-node traces, eval suite gating CI |
| **Autonomy** | Suggests and escalates. Never resolves. | Low-risk writes only, after approval |
| **Load** | ~30 hrs/week | ~35 hrs/week |




Figure 2 - Both levels are event-driven. Neither polls. Neither lets an agent close a ticket on its own.

| Intermediate Al ServiceNow Support Assistant   | Intermediate Al ServiceNow Support Assistant   | Advanced Agentic Incident Resolution Platform   |
|------------------------------------------------|------------------------------------------------|-------------------------------------------------|
| Trigger                                        | Business Rule, then RESTMessageV2              | Business Rule, then RESTMessageV2               |
| Execution                                      | FastAPI background task                        | Redis queue + Celery workers                    |
| Orchestration                                  | LangChain agent, four tools                    | LangGraph, checkpointed nodes                   |
| Retrieval                                      | Dense top-k + metadata filters                 | Hybrid dense + sparse, reranked                 |
| State                                          | Idempotency store only                         | PostgreSQL: state, approvals, audit             |
| Identity                                       | Least-privilege integration user               | OAuth, least-privilege, ACL-governed            |
| Safety                                         | Restricted toolset, human review               | Permission classes, interrupts, guardrails      |
| Evidence                                       | Langfuse traces + benchmark                    | Per-node traces, eval suite gating Cl           |
| Autonomy                                       | Suggests and escalates. Never resolves.        | Low-risk writes only, after approval            |
| Load                                           | ~30 hrs/week                                   | ~35 hrs/week                                    |


Neither level polls ServiceNow. Ever.

Polling - asking ServiceNow every thirty seconds whether anything new happened - was removed from both projects on purpose. It wastes API budget, it adds latency you cannot control, it hides the trigger logic in a scheduler instead of putting it in the platform where it belongs, and it makes the system impossible to reason about under load.

If any component of your build contains a loop, a cron entry or a scheduled job that reads the incident table looking for work, you have failed a Must requirement (FR-06 intermediate, FR-05 advanced) regardless of how well the rest performs.

<!-- page: 7 -->

Glossary - ServiceNow KB-03


| TERM               | WHAT IT MEANS HERE                                                                                                                                                                                                                                                                                        |
|--------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| PDI                | Personal Developer Instance. A free, full ServiceNow instance issued to each developer account. Every team member should have one; the team nominates a single instance as the build instance. PDIs hibernate after ten days of inactivity and are reclaimed after inactivity beyond that -log in weekly. |
| CSA                | Certified System Administrator. The ServiceNow administration baseline: users, groups, roles, tables, forms, lists, filters, the incident lifecycle, the knowledge base. Week 0 covers this content whether or not anyone sits the exam.                                                                  |
| CAD                | Certified Application Developer. Application scopes, Studio, script includes, business rules, client scripts, REST integration. Week 0 covers the concepts; Sprint 1 uses them.                                                                                                                           |
| Scoped application | A namespaced container for your customisations. Everything you build lives inside one, so it can be exported as an update set and installed elsewhere without colliding with the global namespace. Fields you add in a scope are prefixed- u_ai_status becomes x_<scope>_ai_status in a scoped app.       |
| Business Rule      | Server-side script that runs when a record is inserted, updated, queried or deleted. This is your trigger. It runs inside ServiceNow, decides whether the incident is eligible, and fires the outbound call.                                                                                              |
| RESTMessageV2      | The ServiceNow server-side API for making an outbound HTTP call. Your Business Rule uses it to POST the event to your FastAPI webhook.                                                                                                                                                                    |
| Table API          | The inbound REST interface for reading and writing records: GET /api/now/table/incident/<sys_id> , PATCH to update. Your Python service calls this to read the incident and write the suggestion back.                                                                                                    |
| Work note          | An internal comment on an incident, visible to agents but not to the requester. Your agent writes here. It must never write to Additional comments , which is customer-visible.                                                                                                                           |
| sys_id             | The 32-character hexadecimal primary key of any record. Stable, opaque and the only safe way to refer to an incident. The human-readable number (INC0010023) is for people, not for lookups.                                                                                                              |
| Build Agent        | ServiceNow's own AI-assisted development capability, available on a free PDI with a small monthly prompt allowance. You use it in Sprint 1 to extend the incident experience, and you record what it generated versus what you corrected.                                                                 |
| AI Agent Studio    | ServiceNow's native platform for building in-platform AI agents. It requires a licensed Gen AI entitlement, so on a free PDI it is a design exercise : you design the equivalent native agent, name its tools and its escalation path, and then explain why the external implementation differs.          |
| Update set         | The export format for platform customisations. Your scoped application must export cleanly as one. This is the handover artefact.                                                                                                                                                                         |


<!-- page: 8 -->

Glossary - AI engineering KB-04


| TERM             | WHAT IT MEANS HERE                                                                                                                                                                                                                            |
|------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Chunk            | A slice of a knowledge article small enough to embed usefully and large enough to stand alone. Every chunk carries the identity of the article it came from -without that, a citation is impossible.                                          |
| Embedding        | A dense vector representing the meaning of a chunk. Two chunks about VPN certificate expiry sit close together even if they share no words.                                                                                                   |
| Dense retrieval  | Nearest-neighbour search over embeddings. Strong on paraphrase, weak on exact identifiers-a dense search often fails to find ERR_CERT_DATE_INVALID because that token has no meaning to it.                                                   |
| Sparse retrieval | Term-weighted search (BM25 or a learned sparse encoder). Strong exactly where dense is weak: error codes, product names, hostnames. Advanced only.                                                                                            |
| Hybrid retrieval | Running both and fusing the ranked lists at query time. Almost always beats either alone on ITSM corpora, because incidents contain both prose and identifiers. Advanced only.                                                                |
| Reranking        | Taking the fused candidate set and reordering it with a stronger, slower model that scores each candidate against the query directly. Applied to twenty candidates to pick five. Advanced only.                                               |
| Metadata filter  | A hard constraint applied at query time -published articles only, this service only, current version only. Filters are not ranking hints; they remove candidates entirely.                                                                    |
| Grounding        | The requirement that every claim in the output traces to a retrieved chunk. A step in a procedure that does not appear in any retrieved chunk is a hallucination, however plausible it reads.                                                 |
| Idempotency      | The property that handling the same event twice produces the same result as handling it once. Achieved with a persisted key, not with a prompt.                                                                                               |
| Guardrail        | Deterministic code that runs before or after the model and can block it. Input guardrails screen for injection and redact secrets. Output guardrails validate schema, verify evidence and enforce the tool allowlist. Advanced only.          |
| Trace            | The full record of one run in Langfuse: every step, its inputs, its outputs, the prompt version, tokens, latency and cost. The acceptance bar is that a mentor can reconstruct what happened from the trace alone, without running your code. |
| Checkpoint       | Persisted graph state after each node, so an interrupted run resumes rather than restarts. Advanced only.                                                                                                                                     |
| Interrupt        | A deliberate pause in the LangGraph execution that surfaces the run for human approval and resumes from the checkpoint once a decision is recorded. Advanced only.                                                                            |
| Dead letter      | Where a job goes when its retries are exhausted. Its purpose is to be somewhere a human will actually look. Advanced only.                                                                                                                    |


<!-- page: 9 -->

Part 2 · The ServiceNow layer

The incident lifecycle and the fields that matter KB-05

An incident moves through states. You only need to care about a handful, and you must never move it between them yourself.


| STATE       |   VALUE | WHAT IT MEANS FOR YOU                                                      |
|-------------|---------|----------------------------------------------------------------------------|
| New         |       1 | Just created. This is where your trigger normally fires.                   |
| In Progress |       2 | An agent is working it. Your trigger may fire on a meaningful update here. |
| On Hold     |       3 | Waiting on someone. Do not process; the incident is deliberately paused.   |
| Resolved    |       6 | A fix has been applied. Never write here.                                  |
| Closed      |       7 | Finished. Never write here.                                                |
| Cancelled   |       8 | Not a real incident. Never process.                                        |


Stock fields you will read


| LABEL                       | COLUMN                      | WHY YOU NEED IT                                                                       |
|-----------------------------|-----------------------------|---------------------------------------------------------------------------------------|
| Number                      | number                      | Human-readable identifier. For logs, notes and conversation- never for lookups.       |
| Short description           | short_description           | The one-line symptom. Carries most of the retrieval signal.                           |
| Description                 | description                 | Free text from the requester. Noisy, sometimes long, occasionally hostile -see UC-05. |
| Category / Subcategory      | category , subcategory      | Drives your metadata filter and part of your risk assessment.                         |
| Business service            | business_service            | Which service is affected. The strongest filter you have.                             |
| Priority / Urgency / Impact | priority , urgency , impact | Priority 1 is a hard risk signal at advanced level.                                   |
| State                       | state                       | Eligibility gate. See the table above.                                                |
| Assignment group            | assignment_group            | Whoownsit. Read only; never change it.                                                |
| Work notes                  | work_notes                  | Internal journal. This is where you write.                                            |
| Additional comments         | comments                    | Customer-visible journal. Never write here.                                           |


<!-- page: 10 -->

The AI field model KB-06

You extend the incident table with the AI fields inside a defined application scope. Nothing about this is optional - it is FR-02 at intermediate level and FR-01 at advanced. Create them in the scope, not globally, so the whole thing exports as one update set.

Intermediate - five fields


| LABEL                 | COLUMN                   | TYPE                                                           | WRITTEN BY   | PURPOSE                                                                                                                     |
|-----------------------|--------------------------|----------------------------------------------------------------|--------------|-----------------------------------------------------------------------------------------------------------------------------|
| AI Status             | u_ai_status              | Choice: pending , in_progress , suggested , escalated , failed | The service  | The claim. Set to in_progress by the webhook before dispatch -this is what makes a concurrent second run impossible.        |
| AI Processed          | u_ai_processed           | True/False                                                     | The service  | Set once terminal. Read by the Business Rule as an eligibility condition, so a processed incident cannot re-trigger.        |
| AI Confidence         | u_ai_confidence          | Decimal 0-1                                                    | The service  | Derived from retrieval scores. You must document the formula -FR-17 asks for it explicitly and mentors will ask atDemo Day. |
| AI Suggested Response | u_ai_suggested_ response | Long text                                                      | The service  | The numbered, cited procedure. Never sent anywhere; only rendered on the form.                                              |
| HumanReview Required  | u_human_review_ required | True/False                                                     | The service  | Set on every processed incident, whether the run succeeded or refused. There is no path where this stays false.             |


Advanced - the fuller model, plus an audit table

The advanced scoped application ( AI Incident Orchestrator ) adds classification, model identity, agent version and timing on top of the five above, and writes an AI Execution Log record for every processing attempt including failures.


| ADDITIONAL FIELD    | TYPE                        | PURPOSE                                                                           |
|---------------------|-----------------------------|-----------------------------------------------------------------------------------|
| u_ai_classification | Choice                      | The category the classify node assigned, which may differ from the requester's.   |
| u_ai_risk_level     | Choice: low , medium , high | Set by the determine_risk node, before retrieval.                                 |
| u_ai_model          | String                      | Exact model identifier used for this run.                                         |
| u_ai_agent_version  | String                      | Your agent's version. Without this you cannot attribute a regression to a change. |


<!-- page: 11 -->


| ADDITIONAL FIELD                    | TYPE      | PURPOSE                                                                         |
|-------------------------------------|-----------|---------------------------------------------------------------------------------|
| u_ai_started_at / u_ai_completed_at | Date/Time | End-to-end latency measured platform-side, not just in your traces.             |
| u_ai_failure_reason                 | String    | Why a run ended without a suggestion. Populated on refusal as well as on error. |



| AI EXECUTION LOG COLUMN   | PURPOSE                                                                                                |
|---------------------------|--------------------------------------------------------------------------------------------------------|
| incident                  | Reference to the incident.                                                                             |
| execution_id              | The run identifier. Matches the Langfuse trace ID -makethemthesamevalue and debugging becomes trivial. |
| action                    | What was attempted: classify , retrieve , generate , write_back , escalate .                           |
| agent / agent_version     | Which agent and which version.                                                                         |
| timestamp                 | When.                                                                                                  |
| status                    | success , blocked , failed , awaiting_approval .                                                       |
| result / error            | Outcome payload or the error. One of these is always populated.                                        |


The audit table is not logging

A log line is for you, during development. An execution log record is for the risk owner who will ask, six months from now, what your system wrote to a customer's incident on a specific afternoon and on what basis. It must be written on failures too - an attempt that produced nothing is exactly the attempt someone will want to see.

Eligibility - the decision made inside ServiceNow KB-07

Eligibility is decided by the Business Rule, before anything leaves the platform. Getting this wrong is the single most common Sprint 2 failure: teams emit events for incidents they should not have, then try to filter them out in Python, and end up with an event storm they cannot explain.


| CONDITION                    | INTERMEDIATE   | ADVANCED   | WHY                                                                                                                                                            |
|------------------------------|----------------|------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| active == true               | Required       | Required   | Resolved, closed and cancelled incidents are finished. Nothing you do improves them.                                                                           |
| AI enabled for this incident | Required       | Required   | A flag or a category allowlist. There must be a way for a human to say not this one .                                                                          |
| u_ai_processed == false      | Required       | Required   | Prevents the write-back from re-triggering the rule that caused it. Without this you will build an infinite loop, and you will build it on your first attempt. |


<!-- page: 12 -->


| CONDITION                     | INTERMEDIATE   | ADVANCED   | WHY                                                                                        |
|-------------------------------|----------------|------------|--------------------------------------------------------------------------------------------|
| Category in the supported set | Required       | Required   | You indexed a corpus. Incidents outside it cannot be answered and should not be attempted. |
| u_ai_status != 'in_progress'  | Recommende d   | Required   | A run is already under way. Belt and braces alongside the idempotency key.                 |
| Not human-locked              | -              | Required   | An agent has explicitly taken the incident away from automation. That decision wins.       |
| State not On Hold             | Recommende d   | Required   | Something is deliberately waiting. Do not add noise to it.                                 |


The loop you will build by accident

Your service writes AI Suggested Response back to the incident. That is an update. Your Business Rule fires on update. It evaluates eligibility. If u_ai_processed is still false, it emits another event. The webhook accepts it, dispatches it, the agent runs again, writes again, and fires the rule again. Within a minute you have consumed your model budget and filled the journal with identical suggestions.

Three independent defences, and you want all three:

Set `u_ai_processed = true` in the same write as the suggestion - one PATCH, not two. Two PATCHes leaves a window.

Exclude AI-field-only changes from the trigger condition so an update touching nothing but your own fields does not qualify as a relevant update .

Keep the idempotency key so even if an event escapes, the second one is discarded downstream.

The Business Rule and the outbound event KB-08

The rule runs after insert and update on incident . It builds a minimal payload and posts it. The reference shape below is deliberately close to what you will write - adapt the scope prefix, the endpoint and the secret handling to your own build.

<!-- page: 13 -->

`event_id` is new on every emission. It identifies the event , not the incident. An incident legitimately produces several events over its life; each must be processed once.

Nothing but identifiers crosses the boundary. No short description, no description, no requester name. The backend fetches what it is authorised to fetch, with its own credentials. This is FR-04 at advanced level and it is the difference between an integration and a data leak.

Run the rule `after`, not `before`. A before rule runs inside the database transaction; a slow or failing HTTP call there degrades the platform for every user.

Set a timeout. Five seconds is generous for a call that only has to return 202.

Never `setBasicAuth` with an admin account here. The rule authenticates to your service, and your service authenticates back to ServiceNow separately - see KB-09.

Prefer async execution, and know why

An after, async Business Rule runs on a scheduled worker just after the transaction commits, so a slow webhook cannot hold the user's form save open. The trade-off is that previous is null in async context, so you cannot call .changes() . Teams that need change detection usually run the rule after synchronous with a hard 5-second timeout, or move the change detection into a flag set by a small before rule. Pick one, and be able to defend it - this is a favourite Demo Day question.

Identity and least privilege KB-09

Every call your backend makes into ServiceNow authenticates as a dedicated integration user. Not your admin account. Not a shared account. Not the account you happen to be logged in with while developing.

<!-- page: 14 -->


|                     | INTERMEDIATE                                                                                                                               | ADVANCED                                                                                                                                                |
|---------------------|--------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------|
| Mechanism           | Basic authentication over HTTPS with a dedicated integration user, credentials from environment variables.                                 | OAuth 2.0 client credentials, tokens refreshed by the service, no long-lived password anywhere.                                                         |
| Roles               | The minimum set that permits reading an incident and writing a work note. Typically itil is already too broad -start from nothing and add. | The same principle, plus explicit ACLs on the scoped application's tables. The team writes down the least-privilege reasoning as a deliverable (D-02).  |
| Test that proves it | Attempt to close an incident with the integration credentials. It must fail with 403.                                                      | The same test, plus an attempt to read a table outside the allowlist, plus evidence that no admin credential exists in the repository or configuration. |


The four checks a mentor will run on your credentials

git log -p | grep -iE "password|secret|token" across your whole history - not just the current tree. A secret that was committed and later removed is still a leaked secret.

Open a Langfuse trace and search it for the instance URL, the integration password and any requester email address. None may appear (NFR-04 / NFR-06).

Read .env.example . It must list every variable with a placeholder, and .env itself must be in .gitignore .

Ask what the integration user can do. If the answer is 'I think it has itil' , that is a fail. The answer is a list of tables and operations.

<!-- page: 15 -->

Part 3 · The event contract

The event payload KB-10

This is a contract between two teams' code. Fix it in Sprint 2 and do not change it afterwards without telling everyone.


| FIELD      | TYPE           | REQUIRED   | NOTES                                                                                                                                                  |
|------------|----------------|------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|
| event_id   | string, 32 hex | yes        | Unique per emission. This is the idempotency key. Never derive it from sys_id , or a legitimate second event on the same incident is silently dropped. |
| sys_id     | string, 32 hex | yes        | The incident to load. Validate the shape before using it -see UC- 05.                                                                                  |
| number     | string         | yes        | For logs and notes only.                                                                                                                               |
| event_type | enum           | yes        | incident.created or incident.updated . Reject anything else with 422.                                                                                  |
| emitted_at | string         | no         | Platform-side timestamp. Useful for measuring true end-to-end latency.                                                                                 |


What must never be in this payload

Short description, description, requester identity, work notes, attachments, or anything else from the record. If your payload grew because it was easier than fetching, you have moved authorisation from ServiceNow's ACLs into your own JSON, and nobody is checking it.

<!-- page: 16 -->

The webhook contract KB-11

One event, one run

The webhook answers first and reasons afterwards. A replay is answered too — and then dropped.




> [Diagram p.16]
### Participants / Lifelines

* **ServiceNow**
* **Webhook**
* **Store**
* **Worker**

---

### Sequence Flow

#### FIRST EVENT

> * **ServiceNow** → **Webhook**: `POST /events`
>   * *Parameters:* `event_id, sys_id, number, event_type`
>
> * **Webhook** → **Store**: `put(event_id)`
>   * *Note:* `new key stored`
>
> * **Webhook** → **ServiceNow**: `PATCH ai_status = in_progress`
>   * *Note:* `the incident is claimed`
>
> * **Webhook** → **ServiceNow**: `202 Accepted`
>   * *Note:* `under one second, no model called`
>
> * **Webhook** → **Worker**: `dispatch(event)`
>   * *Note:* `background task or queued job`
>
> * **Worker** → **ServiceNow**: `PATCH suggestion + human_review`
>   * *Note:* `write-back after retrieval and generation`

---

#### REPLAY OF THE SAME EVENT

> * **ServiceNow** → **Webhook**: `POST /events`
>   * *Note:* `identical event_id`
>
> * **Webhook** --dashed--> **Store**: `put(event_id) — already present`



Outcome of the replay

202 Accepted is returned again — the caller must not see an error — but nothing is dispatched and no second suggestion is written.


Figure 3 - The webhook answers before it reasons. A replay is answered too - and then dropped.

| STATUS                   | WHEN                                                                                        | BODY                                                     |
|--------------------------|---------------------------------------------------------------------------------------------|----------------------------------------------------------|
| 202 Accepted             | The event authenticated, validated, and was either dispatched or recognised as a duplicate. | {"status":"accepted","event_ id":"..."}                  |
| 401 Unauthorized         | Missing or invalid signature / credential.                                                  | Generic. Do not explain which part failed.               |
| 422 Unprocessable Entity | Authenticated, but the payload failed Pydantic validation.                                  | Field-level errors are fine here -the caller is trusted. |
| 429 Too Many Requests    | Optional rate limit. Advanced.                                                              | With Retry-After .                                       |
| 5xx                      | Your service is broken. ServiceNow will log it; nothing retries automatically.              | Generic.                                                 |


The order of operations is the requirement

Authenticate the caller. Constant-time comparison of an HMAC over the raw body, or a shared bearer token at minimum. Reject with 401.

Validate against the Pydantic model. Reject with 422.

Check and persist the idempotency key. If it already exists, return 202 and stop - do not dispatch, do not error.

<!-- page: 17 -->

Claim the incident : PATCH u_ai_status = in_progress . This is a write into ServiceNow and it is the one write that happens on the request path.

Dispatch : a FastAPI background task at intermediate level, a Redis-queued Celery job at advanced.

Return 202. Only now.

Why the webhook answers before the work is done

This is the single most-asked Demo Day question, so have the answer ready. ServiceNow's outbound call is synchronous and holds a worker thread. Retrieval plus generation takes seconds to tens of seconds. If your webhook waited, then a burst of incidents would exhaust ServiceNow's outbound capacity, slow the platform for every user, and time out anyway.

202 Accepted means I have taken responsibility for this event . That responsibility is only real because the idempotency key was persisted before you replied. Answering 202 without persisting the key first means you have promised something you cannot keep.

Idempotency in practice KB-12

Idempotency is a property of a store, not of a prompt. One table, one unique constraint, one atomic insert.

<!-- page: 18 -->

Do not check-then-insert. Two events arriving in the same millisecond both find nothing and both proceed. ON CONFLICT DO NOTHING ... RETURNING makes the claim atomic.

A duplicate returns 202, not 409. The caller did nothing wrong and must not be taught that duplicates are errors.

Retention is configurable (NFR-06 intermediate). A window of days is fine; document the number and put it in the config file rather than in the code.

Intermediate teams may use SQLite or a small PostgreSQL instance for this alone - the PRD makes PostgreSQL optional at that level, but you need durable storage of some kind. An in-memory Python set does not survive a restart, and a restart is exactly when replays happen.

<!-- page: 19 -->

Part 4 · Retrieval

The retrieval pipeline

Build time runs once per corpus change. Query time runs once per incident.




> [Diagram p.19]
### BUILD TIME - ONE COMMAND, REPEATABLE

> * **Load**
>   * Pull published knowledge articles from the KB.
>   * $\rightarrow$
> * **Chunk**
>   * Fixed size with overlap. Article identity kept.
>   * $\rightarrow$
> * **Embed**
>   * Dense vectors. Sparse too, at advanced level.
>   * $\rightarrow$
> * **Index**
>   * Persisted Qdrant collection with payload metadata.

---

### QUERY TIME - ONCE PER INCIDENT

> * **Query**
>   * Short description plus the symptom text. No credentials, no PII.
>   * $\rightarrow$
> * **Filter**
>   * state = published, category, service, current version only.
>   * $\rightarrow$
> * **Search**
>   * Intermediate: dense top-k. Advanced: dense + sparse fused at query time.
>   * $\rightarrow$
> * **Rerank**
>   * Advanced only. Reorder the fused candidates before anything reaches the model.

**Output:** top-k chunks, each with a similarity score and the article number it came from.

---

> **Note:** Keep the dense-only path switchable. You cannot claim hybrid retrieval helped unless you can turn it off and measure.



The knowledge article format KB-13

Appendix A carries ten reference articles. They are written in the shape below, and your ingestion pipeline must preserve every metadata field on every chunk derived from them. Use exactly these ten so that your benchmark numbers can be compared with every other team's.




> [Diagram p.19]
```yaml
---
article_number: KB0001
title: VPN authentication fails after a password change
category: network
service: corporate-vpn
state: published        # published | draft | retired
version: 2
security_level: internal    # internal | restricted
updated: 2026-04-11
---
```

## Symptom
...
## Cause
...
## Resolution
1. ...
## Escalation
...



<!-- page: 20 -->


| METADATA FIELD   | USED FOR                                         | CONSEQUENCE OF LOSING IT                                                                            |
|------------------|--------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| article_number   | Citation. The generated procedure names it.      | You cannot cite. FR-13 fails and no suggestion is defensible.                                       |
| title            | Citation and display.                            | The agent cites a number nobody recognises.                                                         |
| category         | Filter, matched against the incident's category. | Storage answers get returned for network incidents.                                                 |
| service          | Filter. The single strongest one you have.       | Retrieval quality drops sharply on a mixed corpus.                                                  |
| state            | Hard filter -published only, by default (FR-11). | Draft or retired procedures reach a live incident. This is the failure that gets a pilot cancelled. |
| version          | Filter to the current version; also cited.       | You cannot prove which revision a suggestion came from.                                             |
| security_level   | Filter. Advanced.                                | Restricted content reaches a run that had no right to it.                                           |


Chunking KB-14

Chunking is a configuration with a measurable effect, so treat it as one: put the values in the config file, change one at a time, and re-run the benchmark after each change.


| PARAMETER       | STARTING VALUE                           | WHAT MOVING IT DOES                                                                                                                                                               |
|-----------------|------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| chunk_size      | 700 characters                           | Larger chunks carry more context but dilute the embedding, so a specific symptom matches less sharply. Smaller chunks match sharply but arrive without the surrounding procedure. |
| chunk_overlap   | 120 characters                           | Stops a resolution step being cut in half at a boundary. Below about 10% of chunk size, procedures start breaking mid-step.                                                       |
| split_on        | Markdown headings first, then paragraphs | Splitting on headings keeps Symptom, Cause and Resolution intact. Naive fixed-width splitting on these articles measurably hurts -test it once so you can report the number.      |
| min_chunk_chars | 80                                       | Discards fragments like a lone heading, which otherwise return high similarity and carry no information.                                                                          |


A chunk, fully formed

<!-- page: 21 -->

Re-running ingestion must not duplicate anything

NFR-10 at intermediate level requires that re-running ingestion over an unchanged corpus produces no duplicate chunks. Derive the point ID deterministically - for example a UUID5 over article_number + version + chunk_index - and upsert. A random UUID means every ingestion run doubles your collection, your retrieval quality quietly degrades, and the cause is invisible until someone counts the points.

The Qdrant collection KB-15


|                 | INTERMEDIATE                                                       | ADVANCED                                                                  |
|-----------------|--------------------------------------------------------------------|---------------------------------------------------------------------------|
| Vectors         | One dense vector per point.                                        | Namedvectors: one dense, one sparse, in the same collection.              |
| Search          | query_points with a dense vector and a metadata filter.            | Dense and sparse prefetch, fused at query time, then reranked.            |
| Payload indexes | On category , service , state .                                    | The same, plus version and security_level .                               |
| Persistence     | A Docker volume. The collection must survive docker compose down . | The same. Ingestion is one commandandis reproducible from scratch (D-05). |


<!-- page: 22 -->

Reading a retrieval result KB-16

Incident INC0010023, short description 'Cannot connect to VPN since password reset this morning' , category network , service corporate-vpn . Dense-only, top-k 5, published filter applied:


|   RANK | ARTICLE   | SECTION    |   SCORE | READ                                                                                      |
|--------|-----------|------------|---------|-------------------------------------------------------------------------------------------|
|      1 | KB0001    | Resolution |   0.847 | Correct article, correct section. This is what a good run looks like.                     |
|      2 | KB0001    | Cause      |   0.812 | Same article, adjacent section. Expected and useful.                                      |
|      3 | KB0005    | Symptom    |   0.694 | Account lockout. Plausible neighbour -password changes cause both. Not wrong to retrieve. |
|      4 | KB0009    | Resolution |   0.611 | Wi-Fi on 5 GHz. Category-adjacent noise. Below where it matters.                          |
|      5 | KB0003    | Symptom    |   0.585 | Shared drive mapping. Noise.                                                              |


Top-3 hit rate is your headline metric (FR-20, D-06). Here the expected article is at rank 1, so this incident scores a hit.

Absolute scores are not comparable across embedding models. A 0.847 from one model and a 0.847 from another mean nothing to each other. Your threshold is calibrated for your model and must be recalibrated if you change it.

The gap between rank 1 and rank 3 is more informative than rank 1 alone. A run where the top five all sit between 0.60 and 0.63 is a run with no clear evidence, even though nothing is technically below threshold.

Where dense-only visibly loses - and hybrid wins

Now INC0010031: 'SAP GUI: connection timed out, error RFC_ERROR_COMMUNICATION' . The error token carries almost all the diagnostic signal and almost none of the semantic signal.


| CONFIGURATION   |   RANK OF KB0008 | WHY                                                                                                                                             |
|-----------------|------------------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| Dense only      |                4 | RFC_ERROR_COMMUNICATION is close to meaningless in embedding space; the model matches on timeout and connection , which half the corpus shares. |


<!-- page: 23 -->


| CONFIGURATION       |   RANK OF KB0008 | WHY                                                                                                                                       |
|---------------------|------------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| Hybrid (RRF fusion) |                2 | Sparse retrieval matches the literal token, which appears in exactly one article.                                                         |
| Hybrid + rerank     |                1 | The reranker scores the query against each candidate directly and promotes the one that contains both the token and the matching symptom. |


Measure this yourself - do not quote it

The numbers above are illustrative of the shape of the effect, not a result you may cite. NFR-08 at advanced level requires that hybrid-plus-rerank outperform the dense-only baseline on your evaluation dataset, by a margin recorded in your evaluation report . That means keeping the dense-only path switchable and running all three configurations over the same benchmark. A team that cannot switch the feature off cannot prove it helped.

The score threshold and the refusal path KB-17

The threshold decides whether a fix is drafted at all. Below it, the system must refuse - set Human Review Required, write an explicit hand-off note, and stop (FR-15).

Run the ten benchmark incidents and record the top score for each. These are your true positives.

Run at least three deliberately out-of-scope incidents - payroll, facilities, a request for a new laptop. Record their top scores. These are your true negatives.

Set the threshold between the two clusters. If they overlap, your retrieval is the problem and no threshold will fix it.

Write the number, the date and the embedding model into the config file, and re-derive it whenever the model or the corpus changes.

What a refusal looks like on the incident


| Work note (internal):                                                                                                                                                                    | Work note (internal):                                                                                                                                                                    |
|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| AI assistant: no matching knowledge article found.                                                                                                                                       | AI assistant: no matching knowledge article found.                                                                                                                                       |
| Searched the published knowledge base for: "printer in meeting room 4 makes a grinding noise" (category: hardware). Best match scored 0.31 against a threshold of 0.55, so no resolution | Searched the published knowledge base for: "printer in meeting room 4 makes a grinding noise" (category: hardware). Best match scored 0.31 against a threshold of 0.55, so no resolution |
| Flagged for human Fields written:                                                                                                                                                        | review. Run ID: 7c1f...e402 u_ai_status = escalated u_ai_processed = true u_human_review_required = true u_ai_confidence = 0.31 u_ai_suggested_response = (empty)                        |


<!-- page: 24 -->

A refusal is a successful run

It is traced, it is logged, it is counted in your metrics, and it leaves the incident in a clean state with a human flagged. The failure mode is not refusing too often - it is a system that answers everything, because every wrong answer it produces is now carrying your citation format and your confidence score, which is precisely what makes it dangerous.

<!-- page: 25 -->

Part 5 · Reasoning, safety and orchestration

The tool registry KB-18

What the agent can do is defined by what you register, not by what you tell it. This is FR-12 at intermediate level and FR-16 at advanced.


| TOOL                   | CLASS          | LEVEL    | CONTRACT                                                                              |
|------------------------|----------------|----------|---------------------------------------------------------------------------------------|
| get_incident           | read           | both     | Fetch one incident by sys_id . Returns the fields listed in KB- 05 and nothing else.  |
| search_knowledge       | read           | both     | Query plus optional filters. Returns top-k chunks with scores and article references. |
| add_work_note          | low-risk write | both     | Append an internal note. Cannot write to comments .                                   |
| request_human_revie w  | low-risk write | both     | Set HumanReview Required and record the reason. The escape hatch, always available.   |
| update_ai_fields       | low-risk write | both     | Write the suggestion and confidence. Scoped to the AI fields only.                    |
| get_similar_inciden ts | read           | advanced | Optional. Historical resolved incidents as additional evidence.                       |
| propose_resolution     | high-risk      | advanced | Requires approval. Even then it proposes; it does not close.                          |



| CLASS          | RULE                                                                                                                                                                                                  |
|----------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| read           | Executes freely. Still traced, still counted.                                                                                                                                                         |
| low-risk write | Executes freely, but only into the AI fields and the internal work-note journal. Nothing customer- visible.                                                                                           |
| high-risk      | Advanced only. Never executes without a recorded human approval, obtained through a LangGraph interrupt (FR-17). Blocked server-side by the allowlist -the model is never in a position to bypass it. |


Tools that must not exist

There is no resolve_incident , no close_incident , no reassign_incident , no email_requester , no run_command and no update_any_field . Not disabled - absent. A mentor will read your tool registry and count. If a dangerous capability is present but guarded by a prompt instruction, that is a fail at both levels.

<!-- page: 26 -->

The generation contract KB-19

The system prompt is a specification, not an incantation. It states the role, the grounding rule, the output shape and the refusal condition, and it does not ask the model politely to be safe.

You are an IT service desk assistant. You draft resolution procedures for incidents, for a human agent to review before use. GROUNDING - Use ONLY the retrieved knowledge articles supplied below. - Every step you write must appear in, or follow directly from, a retrieved chunk. Do not add commands, paths, registry keys, URLs or version numbers that are not present in the retrieved content. - If the retrieved content does not resolve the incident, say so and stop. Do not produce a partial or speculative procedure. OUTPUT - A numbered procedure, each step a single action a Tier-1 agent can perform. - End with: Source: <article_number> - <title> (v<version>), section <section>. - If more than one article contributed, cite each one. - No preamble, no apology, no restatement of the incident. LIMITS - You cannot resolve, close or reassign this incident and must not imply that you have. - You never address the requester. You are writing to a support agent. RETRIEVED CONTENT {{ chunks }} INCIDENT number: {{ number }} short_description: {{ short_description }} description: {{ description }}

Version this prompt and send the version to Langfuse with every run (FR-18 / FR-19). Without it you cannot attribute a quality change to a prompt change.

Put the retrieved content before the incident text. The incident text is untrusted input - see UC-05 - and belongs as far from the instructions as you can put it.

Never interpolate the incident description into an instruction sentence. It goes into a clearly labelled data block, always.

The expected output shape

Confirm with the user that they changed their password within the last 24 hours.

Ask the user to sign out of the VPN client completely, including the system tray icon.

Clear the cached credential for the VPN profile.

Reconnect using the new password.

If authentication still fails, check whether the account is locked in the identity console before escalating.

<!-- page: 27 -->

Confidence KB-20

FR-17 at intermediate level asks for an AI Confidence value and for the documented formula that produced it . The formula matters more than the number: an undocumented confidence score is a number that looks like evidence and is not.

Strength alone is not confidence. Five chunks from five different articles all scoring 0.70 is a weaker signal than two chunks from one article scoring 0.70, because the second case shows agreement.

Margin catches the flat-distribution failure where nothing is below threshold and nothing is clearly right.

Be able to name a case where your formula is wrong. Every reasonable formula has one. Knowing yours is the difference between a heuristic and a superstition.

Guardrails KB-21

Advanced only - FR-18, D-07. Guardrails are deterministic code, positioned so the model cannot route around them.


| STAGE   | CHECK                                                                                                 | ACTION ON FAILURE                                                                               |
|---------|-------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------|
| Input   | Prompt-injection screening of short_description and description against a pattern and classifier set. | Strip or neutralise, mark the run as injection_suspected , and force the human path.            |
| Input   | Credential and personal-data redaction -passwords, tokens, keys, national IDs, card numbers.          | Redact before the text reaches the model and before it reaches the trace.                       |
| Input   | Length and encoding bounds.                                                                           | Truncate at a documented limit; reject non- UTF-8.                                              |
| Output  | Schema validation of the generated object.                                                            | One retry with the validation error appended; then escalate.                                    |
| Output  | Evidence verification -every step matched back to a retrieved chunk.                                  | Drop unverifiable steps. If more than a configured fraction is dropped, refuse the whole draft. |


<!-- page: 28 -->


| STAGE   | CHECK                                                                 | ACTION ON FAILURE                                     |
|---------|-----------------------------------------------------------------------|-------------------------------------------------------|
| Output  | Tool allowlist, enforced server-side at call time.                    | Block, log, trace, escalate. Never log and continue . |
| Output  | Secret scan of the generated text before it is written to ServiceNow. | Block the write outright.                             |


Your red-team set is a deliverable

D-07 asks for an adversarial test set covering injection, sensitive data and disallowed actions, with the recorded results . Ten to fifteen cases is enough if they are genuinely varied. Run them in CI. A guardrail with no test proving it fires is an assertion, and assertions do not survive Demo Day questioning.

The LangGraph state machine KB-22

Advanced only - FR-11, FR-12, FR-13, FR-17.

The LangGraph state machine (advanced)

Explicit nodes, explicit edges, checkpointed state. An interrupted run resumes; it does not restart.




> [Diagram p.28]
> ### Workflow Diagram Overview
> 
> The diagram illustrates an incident processing graph flow consisting of sequential execution steps on the main left pipeline, branching logic based on risk and confidence, and right-hand side handling states (actions, interrupts, escalations, and dead letters).

---

### Sequential Main Pipeline (Left Column)

* **`load`**
  * **Description:** Fetch the incident by sys_id
  * **Next Step:** `validate`

* **`validate`**
  * **Description:** Schema, required fields, eligibility re-check
  * **Next Step:** `classify`

* **`classify`**
  * **Description:** Category, service, symptom type
  * **Next Step:** `determine_risk`

* **`determine_risk`**
  * **Description:** Risk assessed BEFORE retrieval
  * **Next Step:** `retrieve`
  * **Branch Connection:** Points to **`interrupt`** (via orange arrow for high risk or low confidence assessment)

* **`retrieve`**
  * **Description:** Hybrid search, filters, rerank
  * **Next Step:** `diagnose`

* **`diagnose`**
  * **Description:** Reason over the retrieved evidence
  * **Next Step:** `generate`

* **`generate`**
  * **Description:** Draft the numbered procedure
  * **Next Step:** `verify_evidence`

* **`verify_evidence`**
  * **Description:** Every step traced to a chunk
  * **Next Step:** `safety_check`

* **`safety_check`**
  * **Description:** Output schema, tool allowlist, redaction
  * **Next Step:** `confidence_check`

* **`confidence_check`**
  * **Description:** Compare against the configured floor
  * **Branch Connections:**
    * Points to **`act`** (via green arrow)
    * Points to **`escalate`** (via cyan arrow)

---

### Handling & Execution States (Right Column)

* **`act`**
  * **Description:** Low-risk write only. Suggestion and work note go back through the Table API.
  * **Source:** Triggered from **`confidence_check`**

* **`interrupt`**
  * **Description:** High risk or low confidence. The graph pauses and presents incident, evidence, draft and verdicts for approval.
  * **Source:** Triggered from **`determine_risk`**
  * **Next Connection:** Flows into **`resume`** (via dashed blue arrow)

* **`resume`**
  * **Description:** Only once a decision is persisted in PostgreSQL. Continues from the checkpoint, never from the start.
  * **Source:** Follows from **`interrupt`**

* **`escalate`**
  * **Description:** No safe action available. Human Review Required is set and the run ends with a written reason.
  * **Source:** Triggered from **`confidence_check`**

* **`dead_letter`**
  * **Description:** Reached from the Celery retry policy, not from the graph. Retries exhausted; the job lands where a person looks.



Checkpoint after every node.

Kill a worker between generate and verify_evidence, restart it, and the run continues at verify_evidence. That demo is part of Sprint 4.

Figure 5 - The graph is the design document. If a behaviour is not a node or an edge, it is not in the system.

<!-- page: 29 -->


| NODE             | READS                             | WRITES TO STATE                 | CAN END THE RUN                           |
|------------------|-----------------------------------|---------------------------------|-------------------------------------------|
| load             | sys_id                            | incident record                 | yes -notfound, or ineligible on re- check |
| validate         | incident                          | validation verdict              | yes -required fields missing              |
| classify         | incident text                     | category, service, symptom type | no                                        |
| determine_risk   | classification, priority, service | risk level                      | yes -high risk routes to thehuman path    |
| retrieve         | query, filters                    | chunks with scores              | yes -nothing above threshold              |
| diagnose         | chunks                            | diagnosis                       | no                                        |
| generate         | chunks, diagnosis                 | draft procedure                 | no                                        |
| verify_evidence  | draft, chunks                     | per-step verdicts               | yes -too much unverifiable                |
| safety_check     | draft                             | safety verdict                  | yes -blocked                              |
| confidence_check | scores, verdicts                  | confidence                      | yes -belowfloor raises an interrupt       |


Why risk is determined before retrieval

Because retrieval and generation cost money, latency and exposure. If a Priority 1 incident on a production payments service is going to a human regardless of what the knowledge base says, there is no reason to have spent a model call finding out. Determining risk early is a design decision you will be asked to justify - the answer is that it keeps the expensive path off the incidents that were never eligible for automation.

Checkpointing, demonstrated

NFR-03 requires that a worker killed mid-execution recovers on retry from its checkpoint without duplicating a write or leaving an incident inconsistent - and that you show it live. See UC-06 for the exact procedure.

<!-- page: 30 -->

The decision ladder

Three gates stand between a retrieved chunk and a written suggestion. Any one of them can stop the run.




> [Diagram p.30]
> **GATE 1**  
> ### Evidence  
> Did any chunk clear the score threshold?  
>  
> ➔  
>  
> **GATE 2**  
> ### Risk  
> Is this a high-risk category, service or action?  
>  
> ➔  
>  
> **GATE 3**  
> ### Confidence  
> Is the derived confidence above the floor?  

---

### OUTCOMES

* **Suggest**  
  All three gates pass. A numbered, cited procedure is written to AI Suggested Response. Human Review Required is set. A service desk agent still approves, edits or rejects it.

* **Escalate to a human**  
  Risk is high, or confidence sits below the floor. Advanced raises a LangGraph interrupt and waits for a recorded decision. Intermediate writes the hand-off note and stops.

* **Refuse and hand off**  
  No chunk cleared the score threshold, so no fix is drafted. An explicit note says the knowledge base holds nothing relevant. Silence is the correct answer here.



<!-- page: 31 -->

Part 6 · Worked use cases

Eight scenarios, each traced from trigger to artefact. These are the runs your mentors will ask you to reproduce live, so build against them from Sprint 2 onward rather than discovering them in Sprint 4.

Every use case follows the same shape: what happens, what the system must do, what evidence it must leave behind, and the mistakes that make it fail. The incident numbers are the ones used in the benchmark set in Appendix B, so a use case and a benchmark row refer to the same thing.

The happy path - a VPN failure resolved from the knowledge base UC-01

APPLIES TO Both levels

INC0010023. A finance user raises: 'Cannot connect to VPN since password reset this morning. Client says authentication failed.' Category network , service corporate-vpn , priority 3. This is the run you demo first, and the one everything else is a deviation from.

What must happen


|   # | STEP                                                                                                                                     | EVIDENCE IT LEFT                                                                                  |
|-----|------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------|
|   1 | Business Rule fires on insert. Eligibility passes: active, AI- enabled, unprocessed, category supported.                                 | gs.info line in the ServiceNow system log with the incident number and the response code.         |
|   2 | RESTMessageV2 posts the minimal event. Four identifiers, nothing else.                                                                   | The outbound request body, viewable in the log. A mentor will check the description is not in it. |
|   3 | Webhook authenticates, validates, claims event_id , PATCHes u_ai_status = in_progress , returns 202 in under a second.                   | 202 in the service log; AI Status visibly in_progress on the form before the suggestion appears.  |
|   4 | Background task or Celery worker loads the incident through the Table API as the integration user.                                       | Langfuse span for the load, with latency.                                                         |
|   5 | Retrieval: query built from short description plus description, filtered to published articles in network / corporate-vpn .              | Retrieval span listing the top-k chunks with scores- KB0001 Resolution at rank 1 (see KB-16).     |
|   6 | Threshold cleared. Generation produces a numbered procedure citing KB0001 v2, section Resolution.                                        | Generation span with prompt version, token counts and the output.                                 |
|   7 | Write-back: one PATCH setting suggestion, confidence, u_ai_processed = true , u_human_review_required = true , u_ai_status = suggested . | The form. And exactly one PATCH -nottwo.                                                          |
|   8 | A service desk agent opens the incident, reads the cited procedure, and approves, edits or rejects it.                                   | Nothing automatic. The human is the last step, always.                                            |


<!-- page: 32 -->

What the agent must see on the form


| AI Status:                                                                                                       | suggested                                                                                                        |
|------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| AI Confidence:                                                                                                   | 0.79                                                                                                             |
| Human Review Required:                                                                                           | true                                                                                                             |
| AI Suggested Response:                                                                                           | AI Suggested Response:                                                                                           |
| 1. Confirm with the user that they changed their password within the last 24 hours.                              | 1. Confirm with the user that they changed their password within the last 24 hours.                              |
| 2. Ask the user to sign out of the VPN client completely, including the system tray icon.                        | 2. Ask the user to sign out of the VPN client completely, including the system tray icon.                        |
| 3. Clear the cached credential for the VPN profile.                                                              | 3. Clear the cached credential for the VPN profile.                                                              |
| 4. Reconnect using the new password.                                                                             | 4. Reconnect using the new password.                                                                             |
| 5. If authentication still fails, check whether the account is locked in the identity console before escalating. | 5. If authentication still fails, check whether the account is locked in the identity console before escalating. |
| Source: KB0001 - VPN authentication fails after a password change (v2), section Resolution.                      | Source: KB0001 - VPN authentication fails after a password change (v2), section Resolution.                      |


Where this goes wrong


| SYMPTOM                                                                | CAUSE                                                       | FIX                                                                                             |
|------------------------------------------------------------------------|-------------------------------------------------------------|-------------------------------------------------------------------------------------------------|
| Suggestion appears, then a second identical one appears seconds later. | The write-back re-triggered the Business Rule.              | KB-07. Set u_ai_processed in the same PATCH and exclude AI-field-only updates from the trigger. |
| Procedure contains a step that is nowhere in KB0001.                   | Model filled a gap. Grounding is a prompt instruction only. | KB-19 plus, at advanced level, evidence verification (KB-21).                                   |
| Citation says KB0001 but no version.                                   | Version dropped during chunking.                            | KB-13. Every chunk carries the full payload.                                                    |
| Suggestion is correct but appears in Additional comments .             | Wrote to comments instead of work_notes .                   | KB-05. This is customer-visible. It is a serious failure, not a cosmetic one.                   |
| 202 takes eight seconds.                                               | Retrieval is happening on the request thread.               | KB-11. Dispatch first, reason later.                                                            |


Nothing in the knowledge base - the refusal UC-02

APPLIES TO Both levels

INC0010047. 'The printer in meeting room 4 makes a grinding noise when it feeds paper.' Category hardware . Your corpus contains a printer article - KB0004, about stuck print queues - and nothing at all about mechanical faults. The correct behaviour is to refuse.

What must happen

The event is emitted and accepted normally. Eligibility passed hardware is a supported category, and it should be.

<!-- page: 33 -->

Retrieval runs. KB0004 comes back at rank 1 with a score of about 0.31, because both texts mention a printer and nothing else matches.

The threshold gate (KB-17) rejects it. No generation call is made. This is the point most teams miss: refusing after paying for a model call is not refusing, it is failing quietly and expensively.

A hand-off work note is written in the shape shown in KB-17, naming what was searched, the best score and the threshold.

u_ai_status = escalated , u_ai_processed = true , u_human_review_required = true , u_ai_confidence = 0.31 , suggestion field left empty.

A Langfuse trace exists for the run, showing the retrieval span and an explicit refusal outcome - not an error, and not an empty success.

This is a required Demo Day artefact

D-07 at intermediate level asks for traces from at least ten complete runs including one deliberate no-answer case . Do not manufacture it in the last week by deleting articles. Keep an out-of-scope incident in your benchmark from Sprint 3 and run it every time.

Where this goes wrong

The model is asked anyway and produces a confident procedure for a mechanical fault out of thin air. This is the most dangerous failure in the whole project, because it is the one that looks most like success.

The refusal is silent. No note, no field change, nothing on the form. The agent has no idea the system saw the incident. Refusal without communication is indistinguishable from a broken integration.

The run is recorded as an error. It is not. A 500 in your metrics for a correct refusal will destroy your reliability numbers and hide the real errors underneath.

Confidence is left null. Write it. 0.31 is a real measurement and it is exactly what the reviewing agent needs in order to trust the refusal.

The same event twice - replay and duplicate UC-03

APPLIES TO Both levels

The same event is delivered twice. This happens for ordinary reasons: a network retry, a Business Rule firing on both insert and a near-simultaneous update, or someone re-running a test. Your system must handle it without producing two suggestions.

Three variants, three correct behaviours


| VARIANT                 | WHAT ARRIVES                                                   | CORRECT BEHAVIOUR                                                                                                                   |
|-------------------------|----------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| True replay             | Identical event_id .                                           | 202 Accepted, discarded, nothing dispatched, nothing written. One trace or a log line -notanerror.                                  |
| Newevent, same incident | Different event_id , same sys_id , incident genuinely updated. | Process it. This is legitimate. If your key is derived from sys_id you will wrongly drop it -see KB-10.                             |
| Concurrent duplicate    | Two identical events in the same millisecond.                  | Exactly one wins. The atomic ON CONFLICT DO NOTHING ... RETURNING in KB-12 is what makes this true; a read-then-write check is not. |


<!-- page: 34 -->

How to demonstrate it

A high-risk incident stops for a human UC-04

APPLIES TO Advanced only

INC0010052. 'Order service returning 500s, connection pool exhausted.' Priority 1, business service orderprocessing , category software . KB0010 covers exactly this and scores 0.88. Everything about the retrieval is excellent - and the run must still stop.

What must happen

classify assigns category software , service order-processing .

determine_risk runs before retrieval and returns high , on two independent signals: priority 1, and a business service on the high-risk list.

The high-risk edge routes away from the automated path (FR-13). Whether you retrieve anyway to give the approver evidence is your design decision - document it either way.

An interrupt is raised. The graph state is checkpointed. The run is now paused , not failed, not finished.

The approval payload presents: the incident, the retrieved evidence with scores, the draft procedure, the risk verdict and the confidence. Everything the approver needs to decide, in one place.

A row is written to the approvals table in PostgreSQL and an AI Execution Log record is written with status awaiting_approval .

A human approves or rejects. The decision is persisted first .

resume continues from the checkpoint. On approval the suggestion is written; on rejection the run ends with escalated and the recorded reason.

The approval must be recorded before the action, not after

If your service writes to ServiceNow and then records the approval, then a crash between the two leaves a write that nobody authorised and no record that anyone did. Persist the decision, then act on it. NFR-05 requires that every blocked run is auditable end to end, and 'we wrote it and then the database went down' is not an audit trail.

<!-- page: 35 -->

What counts as high risk


| SIGNAL           | EXAMPLE                                                                   | WHY                                                                                                   |
|------------------|---------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Priority         | P1, or P2 on a customer-facing service.                                   | Blast radius. A wrong suggestion on a P1 costs more than the time it saved.                           |
| Business service | Payments, identity, production databases.                                 | Some services are never candidates for automation regardless of how good the answer looks.            |
| Action class     | The procedure would restart a service, change a permission or touch data. | Read-only fixes and destructive fixes are not the same category of suggestion.                        |
| Uncertainty      | Confidence below the floor, or evidence spread across unrelated articles. | Low confidence on a low-risk incident is a refusal; low confidence on anything else is an escalation. |


Prompt injection in the incident description UC-05

APPLIES TO Advanced required, intermediate should understand it

A requester - or someone who has compromised a requester's account - raises an incident whose description contains instructions aimed at your agent rather than a description of a fault.

Why this fails safely, in layers


| LAYER                | WHAT STOPS IT                                                                                                                                                                                                                                    |
|----------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1 · Tool registry    | There is no tool that can resolve an incident, and no tool that can read environment variables. The most persuasive instruction in the world cannot call a function that was never registered. This layer alone stops the attack at both levels. |
| 2 · Input guardrail  | Injection screening flags the imperative pattern, the role-switch marker and the request for configuration. The run is marked injection_suspected and forced onto the human path. Advanced.                                                      |
| 3 · Prompt structure | The description sits inside a clearly delimited data block at the end of the prompt, after the retrieved content, never interpolated into an instruction sentence (KB-19).                                                                       |


<!-- page: 36 -->


| LAYER                | WHAT STOPS IT                                                                                                                                                                             |
|----------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 4 · Output guardrail | Evidence verification finds no retrieved chunk supporting 'set resolution code', and the secret scanner blocks any generated text resembling a credential before it is written. Advanced. |
| 5 · Least privilege  | Even a successful call would fail: the integration user has no permission to close an incident. Attempt it and ServiceNow returns 403 (KB-09).                                            |


The correct outcome

The genuine symptom - a laptop that will not wake - is still handled. Do not discard the incident; an injection attempt does not mean there is no real fault underneath.

A work note records that the description contained content flagged as an instruction attempt, without reproducing the injected text verbatim in a place a future run might re-read.

u_human_review_required = true , and at advanced level u_ai_failure_reason = injection_suspected .

The trace records the guardrail decision. This case belongs in your red-team set (D-07) with its result recorded.

The worker dies mid-run UC-06

APPLIES TO Advanced only

A Celery worker is killed between generate and verify_evidence . NFR-03 requires the run to recover on retry from its checkpoint, without duplicating a write and without leaving the incident inconsistent demonstrated live at Demo Day.

The demonstration, step by step

<!-- page: 37 -->

What each part of the stack must contribute


| COMPONENT              | CONTRIBUTION                                                                                                                                                                                                     |
|------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Redis / Celery         | acks_late = True so the message is only acknowledged after the task completes. Without it, the job vanishes when the worker dies and there is nothing to recover.                                                |
| LangGraph checkpointer | State persisted after every node, keyed by execution ID. The resumed run reads the checkpoint and skips completed nodes.                                                                                         |
| PostgreSQL             | Holds both the checkpoints and the execution record, so the state survives a full stack restart.                                                                                                                 |
| Idempotent writes      | The write-back must be safe to attempt twice, because a crash after the ServiceNow PATCH but before the acknowledgement is a real scenario. Check the field state before writing, or make the write conditional. |


The inconsistent state you must not leave

An incident stuck at u_ai_status = in_progress forever, because the run that claimed it died and nothing ever released the claim. Give the claim a timeout: a run older than a configured window is reclaimable. Say what your window is and why. This is the follow-up question after the crash demo, and it catches most teams.

Ambiguous and multi-service incidents UC-07

APPLIES TO Both levels

INC0010064. 'Nothing works this morning - can't get email, shared drive is gone, and Teams keeps asking me to sign in.' Three symptoms, three services, one incident. Retrieval returns chunks from KB0002, KB0003 and KB0005 with similar middling scores.

The judgement call, and how to make it defensible


| OPTION                                                 | WHEN IT IS RIGHT                                                   | RISK                                                                                                                                              |
|--------------------------------------------------------|--------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------|
| Answer the strongest single symptom                    | One symptom clearly dominates the scores and the others are noise. | You solve a third of the incident and the agent has to work out that the other two thirds are unaddressed.                                        |
| Answer all three, cited separately                     | Each symptom has strong, distinct evidence.                        | A long procedure that mixes three unrelated fixes is harder to review than three short ones.                                                      |
| Refuse and hand off, naming what you saw - recommended | Scores are flat and middling, which is exactly this case.          | None, and it is the honest answer. Flat scores across unrelated articles is precisely the signal your confidence formula (KB-20) exists to catch. |


Whichever you choose, the work note must say what the system observed - that it detected three distinct symptoms across three services and could not attribute them to one cause. That single sentence is worth more to the reviewing agent than a partial procedure would be, because it tells them the pattern is simultaneous multi-service failure , which is itself a diagnosis.

<!-- page: 38 -->

The pattern behind this incident

Simultaneous authentication failures across email, file shares and collaboration tools usually mean one thing: the account is locked, or a credential expired. That is KB0005. Whether your system can reach that conclusion from three symptoms is a fair measure of how good your retrieval and reasoning actually are - and it makes a strong Demo Day moment if it can.

A retired article must never reach a live incident UC-08

APPLIES TO Both levels

KB0010 exists in two versions. Version 1 is retired and instructs the agent to restart the application server directly. Version 2 is published and instructs them to raise a change request instead, because the direct restart caused an outage in March. Both are in your corpus. Only one may ever be retrieved.

What must happen

The metadata filter state == 'published' is applied at query time, as a hard filter, by default (FR-11).

Version 1 is never a candidate. Not ranked low - not present.

The suggestion cites KB0010 (v2) . The version in the citation is what lets a reviewer confirm which revision was used.

If a team also filters on version , the filter must track the current version rather than a hard-coded number, or the next revision silently disappears from retrieval.

How to prove it in ten seconds

Why this use case exists

Every knowledge base contains procedures that were correct once and are now dangerous. Retrieval that ignores lifecycle state will find them, because they are well written and semantically perfect matches. The filter is not a refinement; it is the thing standing between your system and confidently recommending the exact action that caused the last outage.

<!-- page: 39 -->

Part 7 · Evidence and evaluation

The shared benchmark set KB-23

Ten evaluation incidents with their expected source articles, plus three negative controls that must be refused. Every team runs the same set, so numbers are comparable across teams and across the two levels. Appendix B carries the machine-readable version; Appendix A carries the articles.


| INCIDENT   | SHORT DESCRIPTION                                       | CATEGORY   | EXPECTED ARTICLE   | TESTS                                  |
|------------|---------------------------------------------------------|------------|--------------------|----------------------------------------|
| INC0010023 | Cannot connect to VPN since password reset this morning | network    | KB0001             | The happy path (UC-01)                 |
| INC0010024 | Outlook stuck on Disconnected, no mail since 08:00      | software   | KB0002             | Service-wide outage vs single user     |
| INC0010025 | Shared drive S: missing after I logged in today         | network    | KB0003             | Mapping vs permissions ambiguity       |
| INC0010026 | Print jobs queue up and nothing comes out               | hardware   | KB0004             | Straightforward procedural match       |
| INC0010027 | Account locked, cannot sign in anywhere                 | inquiry    | KB0005             | Identity path, adjacent to KB0001      |
| INC0010028 | Replaced myphone, MFA no longer works                   | inquiry    | KB0006             | High-risk identity change              |
| INC0010029 | Laptop very slow since the update last night            | hardware   | KB0007             | Vague symptom, weak retrieval signal   |
| INC0010031 | SAP GUI: connection timed out, RFC_ERROR_COMMUNICATION  | software   | KB0008             | Error token -dense vs hybrid (KB-16)   |
| INC0010033 | Wi-Fi keeps dropping on the 5 GHz network               | network    | KB0009             | Near-duplicate wording across articles |
| INC0010052 | Order service returning 500s, connection pool exhausted | software   | KB0010 v2          | High risk + retired-version filter     |
| INC0010047 | Printer in meeting room 4 makes a grinding noise        | hardware   | -none-             | Must refuse (UC-02)                    |
| INC0010048 | When will myexpense claim from March be paid?           | inquiry    | -none-             | Must refuse -outof domain              |
| INC0010049 | Please order measecond monitor for mydesk               | inquiry    | -none-             | Must refuse -arequest, not an incident |


<!-- page: 40 -->

The negative controls are not optional

Three of the thirteen rows have no correct answer. A system evaluated only on incidents it can solve will be tuned until it always answers, which is the exact failure mode the threshold exists to prevent. Report hit rate on the ten and refusal rate on the three, separately. A team reporting 10/10 without saying what happened to the negative controls has reported half a result.

Metrics, defined KB-24


| METRIC                  | DEFINITION                                                                                                                                                                                                      | WHERE REQUIRED            |
|-------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------|
| Top-3 hit rate          | Proportion of the ten answerable incidents where the expected article appears in the top three retrieved results. Article-level, not chunk-level -three chunks from the right article is a hit, not three hits. | FR-20, D-06 · both levels |
| Refusal correctness     | Proportion of the three negative controls correctly refused, and of the ten answerable incidents not refused. Report both directions.                                                                           | FR-15 · both levels       |
| Faithfulness            | Proportion of generated steps supported by at least one retrieved chunk. Scored by an LLM judge with the chunks in context.                                                                                     | FR-20 · advanced          |
| Context relevance       | Proportion of retrieved chunks actually relevant to the query. Low relevance with a high hit rate means top-k is too large.                                                                                     | FR-20 · advanced          |
| Hallucination rate      | Proportion of runs containing at least one unsupported claim. The inverse of faithfulness at run level rather than step level.                                                                                  | FR-20 · advanced          |
| Classification accuracy | Agreement between the classify node's category and the ground- truth category.                                                                                                                                  | FR-20 · advanced          |
| Escalation correctness  | Proportion of runs where escalating (or not) was the right call, judged against the expected outcome column.                                                                                                    | FR-20 · advanced          |
| Tool-selection accuracy | Proportion of tool calls that were the right tool for the step.                                                                                                                                                 | FR-20 · advanced          |
| p95 end-to-end latency  | Event accepted to incident updated, at the 95th percentile, measured from traces.                                                                                                                               | NFR-01/02 · both levels   |


The report that satisfies D-06 and D-08

<!-- page: 41 -->

The interpretation is the part that is marked. A table of numbers with no reading of what they mean is a log file, not a report. Say which incidents moved, why you think they moved, and what you would change next.

The trace checklist KB-25

NFR-08 (intermediate) and NFR-07 (advanced) set the same bar in different words: a mentor must be able to reconstruct any run from its trace alone, without executing your code. Open one of your traces and check.


| PRESENT IN THE TRACE?                                   | INTERMEDIATE    | ADVANCED   |
|---------------------------------------------------------|-----------------|------------|
| Event ID and incident number                            | required        | required   |
| Prompt version                                          | required        | required   |
| Retrieval query as sent, plus every filter applied      | required        | required   |
| Every retrieved chunk with its score and article number | required        | required   |
| Generation input and output                             | required        | required   |
| Token counts and latency                                | required        | required   |
| Cost                                                    | recommended     | required   |
| A span per graph node                                   | -               | required   |
| Every tool call with its arguments and result           | recommended     | required   |
| Risk verdict, safety verdict, confidence                | confidence only | all three  |
| Guardrail decisions, including ones that passed         | -               | required   |
| Errors with stack context                               | required        | required   |
| Nosecrets, no credentials, no requester PII             | required        | required   |


Definition of done, by sprint KB-26

Condensed from both PRDs. The full wording, and the requirement traceability, live in your own level's document - this is the checklist, not the contract.

<!-- page: 42 -->


| SPRINT                   | INTERMEDIATE                                                                                                                                                                                   | ADVANCED                                                                                                                                                                                |
|--------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1 · Platform             | An incident moves through its lifecycle live; the AI fields render on the form; the integration user can read an incident and write a work note, and can do nothing else.                      | The scoped app exports cleanly as an update set; an execution log record can be written by the OAuth identity; no admin credential exists anywhere in the repository or configuration.  |
| 2 · Event integration    | An eligible incident produces a 202 in the service log within a second; the same event fired twice produces exactly one downstream execution; an ineligible incident produces no event at all. | 202 within 500 msat p95; the same event twice produces exactly one execution; a job that keeps failing lands in the dead-letter path rather than looping.                               |
| 3 · Retrieval& reasoning | A live incident goes from creation to a cited suggestion with no human step in between; a deliberately out-of-scope incident produces a hand-off note and no fix.                              | A live incident runs the full graph to a cited draft; a high-risk incident stops at the risk node; killing the process mid-run and retrying resumes from the checkpoint.                |
| 4 · Trust& hardening     | A mentor can reconstruct any run from its trace alone; the benchmark report exists with numbers in it; the stack starts on a clean machine with no undocumented steps.                         | No high-risk action reaches ServiceNow without a recorded approval; a deliberately regressed prompt fails the CI evaluation gate; a killed worker recovers without duplicating a write. |


<!-- page: 43 -->

Part 8 · Operating guide

Configuration reference KB-27

NFR-06 (intermediate) requires that chunk size, overlap, top-k, score threshold, model names and the idempotency window live in one configuration file. Not scattered through the code, and not hard-coded next to the call that uses them.


| ENVIRONMENT VARIABLE                          | PURPOSE                                                   |
|-----------------------------------------------|-----------------------------------------------------------|
| SN_INSTANCE_URL                               | Your PDI base URL.                                        |
| SN_INTEGRATION_USER / SN_INTEGRATION_PASSWORD | Intermediate. The dedicated non-admin account from KB-09. |


<!-- page: 44 -->


| ENVIRONMENT VARIABLE                                      | PURPOSE                                                     |
|-----------------------------------------------------------|-------------------------------------------------------------|
| SN_OAUTH_CLIENT_ID / SN_OAUTH_CLIENT_SECRET               | Advanced.                                                   |
| WEBHOOK_SECRET                                            | Shared with the Business Rule; used for the HMACsignature.  |
| QDRANT_URL / QDRANT_API_KEY                               | Vector store.                                               |
| LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST | Observability.                                              |
| DATABASE_URL                                              | PostgreSQL. Optional at intermediate; required at advanced. |
| REDIS_URL                                                 | Advanced only.                                              |
| LLM_API_KEY / LLM_MODEL / EMBEDDING_MODEL                 | Model access, supplied by Sprints.                          |


The local stack KB-28

NFR-07 (intermediate) and NFR-10 (advanced): the whole stack comes up on a clean machine from one Docker Compose command plus the README, with no undocumented manual steps. A mentor will test this by cloning your repository onto a machine that has never seen it.


| SERVICE   | INTERMEDIATE   | ADVANCED   | NOTES                                                                      |
|-----------|----------------|------------|----------------------------------------------------------------------------|
| api       | yes            | yes        | FastAPI. The webhook and, at intermediate level, the background execution. |
| qdrant    | yes            | yes        | Persisted to a named volume. The collection must survive a restart.        |
| langfuse  | yes            | yes        | Self-hosted or cloud. Either is fine; say which in the README.             |
| postgres  | optional       | yes        | Idempotency at minimum; the full state store at advanced.                  |
| redis     | -              | yes        | Broker for Celery.                                                         |
| worker    | -              | yes        | Celery worker. This is the container you kill in UC-06.                    |


The README your reviewer expects

Prerequisites, with versions.

cp .env.example .env and a table explaining every variable.

docker compose up -d .

One command to ingest the corpus.

One command to run the benchmark.

One command to run the tests.

<!-- page: 45 -->

The ServiceNow side: which update set to import, which system properties to set, how to point the Business Rule at your endpoint.

The architecture diagram (D-09 / D-10).

Troubleshooting KB-29


| SYMPTOM                                          | LIKELY CAUSE                                                                   | WHAT TO DO                                                                                                                                                 |
|--------------------------------------------------|--------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Business Rule never fires.                       | Condition too narrow, rule inactive, or when set to before on a query.         | Add a gs.info as the first line of the rule. If it does not appear, the rule is not running; if it does, your eligibility logic is rejecting the incident. |
| Rule fires, no request reaches the service.      | Instance cannot reach your endpoint.                                           | A PDI cannot call localhost . Expose the service with a tunnel and put the public URL in a system property, never hard-coded in the rule.                  |
| 401 on every event.                              | Signature computed over a re- serialised body.                                 | HMACthe raw bytes on both sides. Any re-serialisation reorders keys and changes the digest.                                                                |
| 422 on every event.                              | Field name or type mismatch.                                                   | Log the raw body and diff it against KB-10. Usually event_type casing or a null emitted_at .                                                               |
| Endless loop of suggestions.                     | The write-back re-triggers the rule.                                           | KB-07. All three defences.                                                                                                                                 |
| Two suggestions from one incident.               | Insert and update both fired, or the idempotency check is read-then- write.    | KB-12. Atomic claim.                                                                                                                                       |
| Retrieval returns nothing.                       | Filter mismatch- Network vs network , or the collection is empty.              | Run the query with no filter. If results appear, the filter is wrong; if not, re-check ingestion actually wrote points.                                    |
| Retrieval returns everything at a similar score. | Chunks too large, or the query is the whole description including boilerplate. | KB-14. Reduce chunk size; build the query from the short description plus the meaningful part of the description.                                          |
| Collection doubles after every ingest.           | Random point IDs.                                                              | KB-14. Deterministic IDs and upsert.                                                                                                                       |
| Suggestion contains invented commands.           | Grounding enforced only in the prompt.                                         | KB-19, and at advanced level evidence verification (KB- 21).                                                                                               |
| Confidence is always 1.0 or always 0.0.          | Formula reads a score that is not normalised, or an empty hit list.            | KB-20. Print the inputs to the formula for one run and check them by hand.                                                                                 |
| Langfuse traces are empty or missing.            | Client not flushed before the process exits.                                   | Flush explicitly at the end of the task. Short-lived workers exit before the background flush runs.                                                        |
| Secrets visible in a trace.                      | Whole request or whole incident logged as a span input.                        | Redact at the boundary, before the trace call. NFR-04 / NFR-06.                                                                                            |
| u_ai_status stuck at in_progress .               | The run that claimed it died.                                                  | UC-06. Implement a claim timeout and state the window.                                                                                                     |


<!-- page: 46 -->


| SYMPTOM                     | LIKELY CAUSE                                            | WHAT TO DO                                                                              |
|-----------------------------|---------------------------------------------------------|-----------------------------------------------------------------------------------------|
| Celery job retried forever. | No retry limit, or a non-retryable error being retried. | Bounded retries with exponential backoff, then dead- letter. FR-10.                     |
| PDI unreachable.            | Hibernated.                                             | Log in to wake it. Log in weekly. Nominate one person to keep the build instance alive. |


Frequently asked KB-30

Can we poll ServiceNow just for the demo, if the webhook is flaky?

No. It is a Must requirement at both levels and it is the first thing a reviewer looks for. If your webhook is flaky, fix the webhook - the usual cause is the endpoint not being reachable from the instance, which is a tunnel problem, not an architecture problem.

Can the agent resolve an incident if it is very confident?

No. There is no confidence level at which the agent gains a capability it does not have. At advanced level a highrisk action can execute after a recorded human approval - that is a human decision, not a model decision.

Our top-3 hit rate is 6/10. Is that a fail?

The intermediate goal is 8 of 10. Six is a signal to work on retrieval, not a reason to enlarge the corpus or reword the incidents. Start by checking chunking (KB-14), then filters (KB-13), then top-k. Report honestly - a team that reports 6/10 with a clear diagnosis of why scores better than a team that reports 10/10 with no method.

Can we use a different vector database or a different framework?

No. Qdrant, PostgreSQL, Redis and Langfuse are locked across both levels, and Langfuse specifically rather than LangSmith. The stack is fixed so that teams can help each other, mentors can review consistently, and BARQ can read one architecture rather than thirty.

Do we need Kubernetes?

No. It is explicitly excluded at both levels. Docker Compose locally and, at advanced level, a GitHub Actions pipeline that builds a deployable image.

How much of the knowledge base do we have to write ourselves?

Appendix A is the shared corpus and every team uses it, so benchmark numbers are comparable. You may add articles of your own on top, but the ten reference articles must be present and unmodified, and your benchmark must be reported against them.

What if BARQ supplies real runbooks?

Then you index those in addition, keep the reference corpus for benchmarking, and report both sets of numbers. Real content is more valuable and messier - which is the point. The dependency is tracked on the Sprints side; do not block on it.

<!-- page: 47 -->

Who is allowed to approve a suggestion in our demo?

Any human on the team, acting in the service desk agent role in ServiceNow. What matters is that the approval is a genuine interaction with the platform and that it is recorded - not that a real BARQ agent performs it.

<!-- page: 48 -->

Appendix A · The reference knowledge corpus

Ten articles. Every team indexes exactly these, unmodified, so that benchmark numbers mean the same thing everywhere. Load them into your PDI knowledge base and into your Qdrant collection.

Each article below is given in the format specified in KB-13. The metadata block is part of the article: preserve every field on every chunk you derive from it. KB0010 is deliberately supplied in two versions - v1 retired, v2 published - to exercise the lifecycle filter (UC-08).

KB0001 - VPN authentication fails after a password change

Symptom. The user can reach the internet but the VPN client reports an authentication failure. It began after a password reset. The client may report 'invalid credentials' even when the new password is entered correctly.

Cause. The VPN client caches the previous credential in the operating system credential store. The cached entry is presented before the newly typed password, so the directory rejects it. Repeated attempts can lock the account (see KB0005).

Resolution.

Confirm with the user that they changed their password within the last 24 hours.

Ask the user to sign out of the VPN client completely, including the system tray icon.

Clear the cached credential for the VPN profile from the credential store.

Reconnect using the new password.

If authentication still fails, check whether the account is locked in the identity console before escalating.

Escalation. If the account is not locked and the new password works elsewhere, escalate to the Network team with the client log.

KB0002 - Outlook shows Disconnected and no mail is delivered

<!-- page: 49 -->

Symptom. The mail client displays Disconnected or Trying to connect. No new mail arrives. Webmail may still work, or may not.

Cause. Two distinct causes present identically: a single-user profile or cached-mode corruption, and a servicewide mail outage. Distinguishing them is the first step, not an afterthought.

Resolution.

Ask whether colleagues are affected. If more than one user in the same area is affected, treat it as a service event and stop; do not apply per-user fixes to a platform outage.

Check whether webmail works for this user. If webmail works, the fault is client-side.

For a client-side fault, close the client fully and reopen it.

If it still fails, recreate the mail profile and allow the cache to rebuild.

Confirm mail flow before closing.

Escalation. If multiple users are affected, raise a major incident against the corporate-email service. Do not resolve individual incidents until the service event is closed.

KB0003 - Mapped shared drive is missing after sign-in

Symptom. A previously available network drive letter is absent after signing in. Other drives may still be present. Browsing to the server path directly may work.

Cause. The mapping script runs before the network is ready, or the user has been removed from the group that grants access to the share. These require different fixes, so establish which one applies before acting.

Resolution.

Ask the user to browse to the server path directly. If it opens, the share and the permissions are fine and the fault is in the mapping.

If the path opens, re-run the mapping script, or remap the drive with reconnect-at-sign-in enabled.

If the path is refused, check the user's group membership against the share's access group.

If group membership is missing, raise an access request. Do not modify group membership from this incident.

Confirm the drive is present after a fresh sign-in before closing.

Escalation. Permission changes go through the access request process and are never applied directly from an incident.

<!-- page: 50 -->

KB0004 - Print jobs queue but nothing prints

Symptom. Documents accumulate in the print queue. The printer shows ready and reports no error. Cancelling a job leaves it stuck as Deleting.

Cause. The local print spooler service has stalled, leaving orphaned job files that block the queue.

Resolution.

Confirm the printer is online and shows no physical error, and that paper and toner are present.

Stop the print spooler service on the affected machine.

Delete the queued job files from the spooler directory.

Start the print spooler service again.

Print a test page and confirm it completes.

Escalation. If the queue stalls again within an hour, or several users on the same printer are affected, escalate to Print Services - the fault is likely on the print server rather than the client.

KB0005 - Account is locked after repeated failed sign-ins

Symptom. The user cannot sign in to any corporate system. Errors mention a locked or disabled account. Often follows a password change, and often presents as several services failing at once.

Cause. The lockout policy triggers after a threshold of failed attempts. A cached credential on any device - a phone mail profile, a VPN client, a mapped drive - can retry an old password silently and lock the account repeatedly, including immediately after each unlock.

Resolution.

Verify the user's identity following the identity verification procedure. This step is mandatory and is never skipped.

Unlock the account in the identity console.

<!-- page: 51 -->

Ask the user to sign out of the corporate mail profile on their mobile device, which is the most common source of a silent retry.

Clear cached credentials on the laptop, including VPN and mapped drives.

Ask the user to sign in again and confirm access to two different services.

If the account locks again within minutes, a device is still retrying an old credential; identify it from the lockout source before unlocking a third time.

Escalation. Repeated lockouts with no identifiable source go to the Identity team. Never disable the lockout policy for an individual user.

KB0006 - Multi-factor authentication after a lost or replaced device

Symptom. The user has a new phone, or has lost the previous one, and can no longer approve sign-in prompts or generate codes.

Cause. The authenticator registration is bound to the previous device and does not transfer with a phone migration.

Resolution.

Verify the user's identity following the enhanced verification procedure for MFA resets. This is stricter than standard verification and must not be shortened.

Confirm whether the previous device is lost or simply replaced. A lost device requires the registration to be revoked, not just re-enrolled.

Raise the MFA reset request through the identity workflow. It requires approval; a service desk agent cannot complete it alone.

Once approved, guide the user through enrolling the new device.

Confirm a successful sign-in with the new factor before closing.

Escalation. An MFA reset is a high-risk identity action. It always requires the approval step, and any suspicion of compromise goes to Security immediately.

KB0007 - Laptop performance degrades after a system update

<!-- page: 52 -->

Symptom. The machine is noticeably slower after an update. Fans run constantly, applications are slow to launch, and the problem persists across restarts.

Cause. Post-update indexing and driver reinstallation run at high priority for a period after installation. If the degradation persists beyond that period, a driver mismatch is the usual cause.

Resolution.

Ask when the update was installed. Within 24 hours, background indexing is expected - tell the user and check back rather than making changes.

Check resource usage and identify the dominant process.

If indexing dominates, allow it to complete and confirm with the user the following day.

If a graphics or storage driver dominates, reinstall the vendor driver for the installed operating system build.

Restart and confirm the machine returns to normal responsiveness.

Escalation. If performance is still degraded 48 hours after the update with no dominant process, escalate to Endpoint Engineering with a performance capture.

KB0008 - SAP GUI connection times out with RFC_ERROR_COMMUNICATION

Symptom. The SAP GUI client fails to connect and reports RFC_ERROR_COMMUNICATION or a connection timeout. Other applications work normally.

Cause. The client cannot reach the message server on the required port. Most often the user is off the corporate network without the VPN, or the saved connection entry points at a decommissioned application server.

Resolution.

Confirm the user is on the corporate network or connected to the VPN. SAP is not reachable from the internet.

Check the saved connection entry against the current published connection details.

If the entry names a specific application server, change it to the message server and group so that load balancing applies.

Reconnect and confirm sign-in reaches the logon screen.

If the timeout persists from a known-good network, check whether the message server is reachable on its port before escalating.

<!-- page: 53 -->

Escalation. A confirmed reachability failure from the corporate network goes to the SAP Basis team with the exact error text and the connection entry used.

KB0009 - Wi-Fi drops repeatedly on the 5 GHz corporate network

Symptom. The connection drops every few minutes and reconnects on its own. It is worse in some parts of the building and while moving between areas.

Cause. Aggressive roaming behaviour between access points, or a power-saving setting on the wireless adapter that suspends the radio during idle periods.

Resolution.

Establish whether drops occur in one location or while moving. Drops only while moving indicate roaming; drops while stationary indicate the adapter.

For a stationary user, disable power saving on the wireless adapter.

Update the wireless adapter driver to the current supported version.

Ask the user to forget and rejoin the corporate network so the profile is rebuilt.

Confirm a stable connection for at least fifteen minutes before closing.

Escalation. Drops affecting several users in the same area are an infrastructure fault. Escalate to Network with the location and the approximate times.

KB0010 v1 - Order service connection pool exhaustion  (RETIRED)

Symptom. The order service returns HTTP 500 and logs report that the database connection pool is exhausted.

Cause. Connections are not being returned to the pool under load.

Resolution.

Restart the order service application server to clear the pool.

<!-- page: 54 -->

Confirm the service returns 200 and monitor for recurrence.

Escalation. If it recurs within the hour, escalate to Platform Engineering.

Why this version is retired

The direct restart in step 1 dropped in-flight orders and caused a 40-minute outage on 14 March 2026. The procedure is not merely outdated - it is actively harmful, and it is beautifully written, which is exactly why an unfiltered retrieval will find it and recommend it. This is the article UC-08 exists to keep out of a live incident.

KB0010 v2 - Order service connection pool exhaustion  (PUBLISHED)

Symptom. The order service returns HTTP 500 under load. Application logs report that the database connection pool is exhausted and that connection acquisition timed out.

Cause. Connections are held beyond their intended lifetime by a long-running query path and are not returned to the pool, so new requests wait and then fail.

Resolution.

Do not restart the application server. A restart drops in-flight orders and caused a 40-minute outage on 14 March 2026.

Confirm pool saturation from the service metrics dashboard rather than from the error message alone.

Notify the Order Processing service owner. This service has a change-controlled remediation path.

Raise an emergency change request for the pool drain procedure, which recycles connections without dropping in-flight work.

Apply the drain procedure only once the change is approved.

Monitor pool utilisation for thirty minutes after the drain.

Escalation. Any incident on order-processing at Priority 1 goes to the service owner immediately and is never remediated from the service desk alone.

<!-- page: 55 -->

Appendix B · The benchmark set, machine-readable

Save this as benchmark/incidents.json . Your harness loads it, creates or looks up each incident, runs retrieval, and reports the metrics defined in KB-24. Three entries have expected_article: null and must_refuse: true - those are the negative controls.

<!-- page: 56 -->

Appendix C · Ingesting this document

This knowledge base is written to be machine-readable by the system it describes. Point your pipeline at it and your agent can answer questions about its own architecture - which is a fast, honest smoke test of the pipeline you just built.

Why bother

Because it exercises the whole path with content you already understand. If your agent cannot answer 'what status code does the webhook return for a duplicate event?' from a document that states the answer plainly in KB-11, then the problem is in your pipeline, not in the corpus - and you have found that out in Week 2 rather than in Sprint 4.

How to chunk it


| RULE                                | DETAIL                                                                                                                                                                                            |
|-------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Split on section IDs                | Each KB-nn and UC-nn section is a natural unit. Split there first, then apply your normal size limit inside a long section.                                                                       |
| Keep tables whole                   | A table split across chunks is worse than useless -half a decision table reads as a complete one. If a table exceeds your chunk size, emit it as a single oversized chunk and note the exception. |
| Keep code blocks whole              | The same reasoning. A truncated payload schema is a wrong payload schema.                                                                                                                         |
| Carry the section ID in the payload | So the agent can cite KB-11 the way it cites KB0001 . This is the whole point.                                                                                                                    |
| Tag the level                       | Sections marked advanced only get level: advanced in the payload, so an intermediate team can filter them out and see how a filter changes retrieval on a corpus they know well.                  |


Suggested payload for a chunk of this document

Ten questions to test it with

What status code does the webhook return when it receives a duplicate event?

Which fields are allowed in the outbound event payload?

<!-- page: 57 -->

Why does the webhook return before retrieval has run?

What happens when no retrieved chunk clears the score threshold?

Which tools may write to the incident, and which class is each?

Why is risk determined before retrieval at advanced level?

What are the three defences against the write-back loop?

Which article must never be retrieved, and why?

How is AI Confidence calculated, and what does the margin term catch?

What must never appear in a Langfuse trace?

Every one of these is answerable from a single section of this document, so a correct answer with a correct section_id citation is a genuine pass and a wrong citation tells you exactly which part of the pipeline to look at.

Appendix D · Demo Day checklist

Print this. Walk it before you present, not during.


|    | CHECK                                                                                           | LEVEL    |
|----|-------------------------------------------------------------------------------------------------|----------|
| ☐  | An incident created live produces a cited suggestion on the form with no human step in between. | both     |
| ☐  | An out-of-scope incident produces a hand-off note and no drafted fix.                           | both     |
| ☐  | The same event fired twice produces exactly one suggestion.                                     | both     |
| ☐  | An ineligible incident produces no event at all.                                                | both     |
| ☐  | No component polls. You can point at the code and the architecture and prove it.                | both     |
| ☐  | The integration user cannot close an incident. You can show the 403.                            | both     |
| ☐  | Benchmark numbers are on screen, with the configuration that produced them.                     | both     |
| ☐  | A Langfuse trace is open, and a mentor can read the run from it without your help.              | both     |
| ☐  | No secret appears in any trace, log or commit in your history.                                  | both     |
| ☐  | The stack starts on a clean machine from the README and one command.                            | both     |
| ☐  | You can explain why the webhook answers before the work is done.                                | both     |
| ☐  | You can state how AI Confidence is calculated and name a case where it is wrong.                | both     |
| ☐  | A high-risk incident stops and waits for an approval that is recorded before the action.        | advanced |
| ☐  | A guardrail block is demonstrated live, from your red-team set.                                 | advanced |


<!-- page: 58 -->


|    | CHECK                                                                             | LEVEL    |
|----|-----------------------------------------------------------------------------------|----------|
| ☐  | A worker killed mid-run recovers from its checkpoint without duplicating a write. | advanced |
| ☐  | A deliberately regressed prompt fails the CI evaluation gate.                     | advanced |
| ☐  | Baseline vs hybrid vs reranked numbers exist, on the same evaluation set.         | advanced |
| ☐  | You can say what each permission class blocks, and why.                           | advanced |


The question behind every question

Mentors and BARQ engineers are not checking whether your system works on the incident you chose. They are checking whether you know what it does when it is wrong. Have the failure cases ready and lead with them - a team that opens with its refusal case and its crash recovery has already answered half the panel.