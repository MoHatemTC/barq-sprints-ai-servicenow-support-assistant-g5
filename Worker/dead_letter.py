import logging

from App.database import db


logger = logging.getLogger("incident.dead_letter")


async def on_dead_letter(
    event: dict,
    error: Exception | str,
    attempts: int,
) -> None:
    """
    Moves a failed event to the Dead-Letter Queue.

    This is called when:
    - A permanent error occurs.
    - All retry attempts are exhausted.
    """

    event_id = event["event_id"]

    error_message = str(error)

    await db.save_dead_letter(
        event_id=event_id,
        payload=event,
        error=error_message,
        attempts=attempts,
    )

    logger.error(
        "Event dead-lettered",
        extra={
            "event_id": event_id,
            "sys_id": event.get("sys_id"),
            "attempt": attempts,
            "outcome": "dead_lettered",
        },
    )