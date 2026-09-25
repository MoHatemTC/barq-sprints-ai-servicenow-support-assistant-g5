import logging
import asyncio
import os
import random
from importlib import import_module
import httpx
from Schemas.webhook_schema import IncidentPayload
from Schemas.incident_worker import WorkerPayload
from App.database import db
from Services.incident_preparer import IncidentContextPreparer
from Worker.celery_app import celery_app
from Worker.errors import RetryableError, PermanentError
from Worker.dead_letter import on_dead_letter


logger = logging.getLogger("incident task by celery")

preparer = IncidentContextPreparer(max_chars=4000)

def load_incident_handler():
    """
    Load the incident handler from the INCIDENT_HANDLER
    environment variable.

    Example:
        Worker.incident_handler.handle_incident
    """

    handler_path = os.getenv("INCIDENT_HANDLER")

    if not handler_path:
        raise RuntimeError(
            "INCIDENT_HANDLER is not configured"
        )

    module_path, function_name = handler_path.rsplit(".", 1)

    module = import_module(module_path)

    handler = getattr(module, function_name, None)

    if not callable(handler):
        raise RuntimeError(
            f"INCIDENT_HANDLER '{handler_path}' is not callable"
        )

    return handler


incident_handler = load_incident_handler()




def calculate_retry_delay(retry_number: int) -> int:
    """
    Calculates an exponential backoff delay with jitter.

    Example:
        retry 0 -> about 2 seconds
        retry 1 -> about 4 seconds
        retry 2 -> about 8 seconds
    """

    base_delay = 2

    exponential_delay = base_delay * (2 ** retry_number)

    jitter = random.uniform(0, 2)

    return int(exponential_delay + jitter)


async def initialize_incident(
    payload: IncidentPayload,
    event_id: str,
):
    # 1. Run the payload through the security firewall
    incident_context = preparer.process_payload(
        sys_id=payload.sys_id,
        number=payload.number,
        short_desc=payload.short_description or "",
        desc=payload.description or "",
    )

    # 2. Secure logging (no raw payload, to avoid PII in logs)
    logger.info(
        "Guardrails applied successfully. Payload sanitized.",
        extra={
            "incident_number": incident_context.original_number,
            "is_safe": incident_context.is_safe,
            "extracted_tags": incident_context.extracted_tags,
            "truncated_length": len(
                incident_context.truncated_description
            ),
        },
    )

    logger.info(
        "Guardrails applied | %s | safe=%s | tags=%s | desc_len=%d",
        incident_context.original_number,
        incident_context.is_safe,
        incident_context.extracted_tags,
        len(incident_context.truncated_description),
    )

    # 3. Short-circuit on malicious payloads
    if not incident_context.is_safe:
        logger.warning(
            f"PROMPT INJECTION BLOCKED for incident {payload.number}.",
            extra={
                "sys_id": payload.sys_id,
            },
        )

        await db.update_event_status(
            event_id,
            "flagged_malicious",
        )

        return {
            "status": "rejected",
            "number": payload.number,
            "message": "Payload rejected due to security policy.",
        }

    return incident_context


async def fetch_incident(sys_id: str):
    """
    Fetches the latest incident from ServiceNow.

    Error classification:
        - Network timeout/request error -> RetryableError
        - HTTP 429 -> RetryableError
        - HTTP 5xx -> RetryableError
        - HTTP 4xx except 429 -> PermanentError
        - HTTP 2xx -> return incident data
    """

    instance_url = os.getenv("SERVICENOW_INSTANCE_URL")
    username = os.getenv("SERVICENOW_USERNAME")
    password = os.getenv("SERVICENOW_PASSWORD")

    if not instance_url:
        raise RuntimeError(
            "SERVICENOW_INSTANCE_URL is not configured"
        )

    if not username:
        raise RuntimeError(
            "SERVICENOW_USERNAME is not configured"
        )

    if not password:
        raise RuntimeError(
            "SERVICENOW_PASSWORD is not configured"
        )

    url = f"{instance_url}/api/now/table/incident/{sys_id}"

    # Network errors are transient.
    # Convert httpx exceptions into RetryableError
    # so Celery can retry the task.
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                url,
                auth=(username, password),
                headers={
                    "Accept": "application/json",
                },
            )

    except (
        httpx.TimeoutException,
        httpx.RequestError,
    ) as exc:

        logger.warning(
            "ServiceNow request failed due to network error",
            extra={
                "sys_id": sys_id,
                "outcome": "retryable_network_error",
            },
        )

        raise RetryableError(
            "ServiceNow request failed due to a network error"
        ) from exc

    # 1. Rate limit -> retry
    if response.status_code == 429:
        raise RetryableError(
            "ServiceNow rate limit exceeded"
        )

    # 2. Server error -> retry
    if 500 <= response.status_code < 600:
        raise RetryableError(
            f"ServiceNow server error: {response.status_code}"
        )

    # 3. Client error -> no retry
    if 400 <= response.status_code < 500:
        raise PermanentError(
            f"ServiceNow client error: {response.status_code}"
        )

    return response.json()["result"]


@celery_app.task(
    bind=True,
    max_retries=2,
)
def process_incident_worker(self, incident):

    async def run():

        # --------------------------------------------------
        # 1. Validate the worker payload
        # --------------------------------------------------
        worker_payload = WorkerPayload(**incident)

        # --------------------------------------------------
        # 2. Check if this event was already completed
        # --------------------------------------------------
        is_completed = await db.is_event_completed(
            worker_payload.event_id
        )

        if is_completed:
            logger.info(
                "Skipping already completed event",
                extra={
                    "event_id": worker_payload.event_id,
                    "sys_id": worker_payload.sys_id,
                    "outcome": "skipped_already_completed",
                },
            )

            return {
                "status": "already_completed",
                "event_id": worker_payload.event_id,
                "sys_id": worker_payload.sys_id,
            }

        # --------------------------------------------------
        # 3. Fetch the latest incident from ServiceNow
        # --------------------------------------------------
        try:
            response = await fetch_incident(
                worker_payload.sys_id
            )

        # --------------------------------------------------
        # 4. Permanent error -> send directly to DLQ
        # --------------------------------------------------
        except PermanentError as exc:

            attempts = self.request.retries + 1

            await on_dead_letter(
                event=incident,
                error=exc,
                attempts=attempts,
            )

            await db.update_event_status(
                worker_payload.event_id,
                "dead_lettered",
            )

            return {
                "status": "dead_lettered",
                "event_id": worker_payload.event_id,
                "sys_id": worker_payload.sys_id,
                "attempts": attempts,
            }

        # --------------------------------------------------
        # 5. Retryable error -> retry or send to DLQ
        # --------------------------------------------------
        except RetryableError as exc:

            attempts = self.request.retries + 1

            # We still have retry attempts available.
            if self.request.retries < self.max_retries:

                retry_delay = calculate_retry_delay(
                    self.request.retries
                )

                logger.warning(
                    "Retryable error, scheduling retry",
                    extra={
                        "event_id": worker_payload.event_id,
                        "sys_id": worker_payload.sys_id,
                        "attempt": attempts,
                        "outcome": "retry",
                        "retry_delay": retry_delay,
                    },
                )

                raise self.retry(
                    exc=exc,
                    countdown=retry_delay,
                )

            # --------------------------------------------------
            # All retry attempts have been exhausted.
            # Move the event to the DLQ.
            # --------------------------------------------------
            await on_dead_letter(
                event=incident,
                error=exc,
                attempts=attempts,
            )

            await db.update_event_status(
                worker_payload.event_id,
                "dead_lettered",
            )

            return {
                "status": "dead_lettered",
                "event_id": worker_payload.event_id,
                "sys_id": worker_payload.sys_id,
                "attempts": attempts,
            }

        # --------------------------------------------------
        # 6. Convert ServiceNow response into IncidentPayload
        # --------------------------------------------------
        incident_payload = IncidentPayload(
            sys_id=response["sys_id"],
            number=response["number"],
            short_description=response["short_description"],
            description=response.get(
                "description",
                "",
            ),
        )

        # --------------------------------------------------
        # 7. Run security guardrails
        # --------------------------------------------------
        incident_context = await initialize_incident(
            incident_payload,
            worker_payload.event_id,
        )

        # --------------------------------------------------
        # 8. If the payload was malicious,
        #    processing is finished.
        # --------------------------------------------------
        if isinstance(incident_context, dict):

            await db.mark_event_completed(
                worker_payload.event_id
            )

            return incident_context

        # --------------------------------------------------
        # 9. Run the AI pipeline
        # --------------------------------------------------
        result = incident_handler(
            incident_context
            )

        # --------------------------------------------------
        # 10. Mark the event as completed
        # --------------------------------------------------
        await db.mark_event_completed(
            worker_payload.event_id
        )

        # --------------------------------------------------
        # 11. Return the AI result
        # --------------------------------------------------
        return result

    return asyncio.run(run())
