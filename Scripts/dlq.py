import argparse
import asyncio
import json
import logging
import os
import sys



# project modules.
PROJECT_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
    )
)

sys.path.insert(0, PROJECT_ROOT)


from dotenv import load_dotenv


# Load environment variables before importing project modules.
# This ensures DATABASE_URL, REDIS_URL, and other settings
# are available when the project modules are imported.
load_dotenv()


from App.database import db
from Worker.tasks import process_incident_worker


logger = logging.getLogger("dlq.cli")


async def inspect_dlq() -> None:
    """
    Displays events currently stored in the Dead-Letter Queue.
    """

    if not db.pool:
        raise RuntimeError(
            "Database connection pool is not initialized."
        )

    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                event_id,
                payload,
                error,
                attempts,
                created_at,
                updated_at
            FROM dead_letter_events
            ORDER BY created_at ASC
            """
        )

    if not rows:
        print("DLQ is empty.")
        return

    print(f"\nDLQ events: {len(rows)}\n")

    for row in rows:
        payload = row["payload"]

        # asyncpg may return JSONB as a string
        # depending on the configuration.
        if isinstance(payload, str):
            payload = json.loads(payload)

        print("-" * 60)
        print(f"Event ID : {row['event_id']}")
        print(f"Sys ID   : {payload.get('sys_id')}")
        print(f"Number   : {payload.get('number')}")
        print(f"Attempts : {row['attempts']}")
        print(f"Error    : {row['error']}")
        print(f"Created  : {row['created_at']}")
        print(f"Updated  : {row['updated_at']}")

    print("-" * 60)


async def requeue_event(event_id: str) -> None:
    """
    Requeues one selected DLQ event back to Celery.
    """

    if not db.pool:
        raise RuntimeError(
            "Database connection pool is not initialized."
        )

    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                event_id,
                payload
            FROM dead_letter_events
            WHERE event_id = $1
            """,
            event_id,
        )

    if not row:
        print(f"Event not found in DLQ: {event_id}")
        return

    payload = row["payload"]

    if isinstance(payload, str):
        payload = json.loads(payload)

    # Send the original worker payload back to Celery.
    # Celery will publish it to Redis using REDIS_URL
    # from the environment.
    task = process_incident_worker.delay(payload)

    # Remove the event from the DLQ only after Celery
    # successfully accepted the task submission.
    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM dead_letter_events
            WHERE event_id = $1
            """,
            event_id,
        )

    print(f"Event requeued successfully: {event_id}")
    print(f"Celery task ID: {task.id}")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect and requeue Dead-Letter Queue events."
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    # ---------------------------------------------------------
    # Inspect command
    # ---------------------------------------------------------
    subparsers.add_parser(
        "inspect",
        help="Show events currently in the DLQ.",
    )

    # ---------------------------------------------------------
    # Requeue command
    # ---------------------------------------------------------
    requeue_parser = subparsers.add_parser(
        "requeue",
        help="Requeue one event from the DLQ.",
    )

    requeue_parser.add_argument(
        "event_id",
        help="Event ID to requeue.",
    )

    args = parser.parse_args()

    # db.connect() reads the PostgreSQL configuration
    # from the environment:
    #
    # DATABASE_URL
    # or
    # POSTGRES_USER
    # POSTGRES_PASSWORD
    # POSTGRES_HOST
    # POSTGRES_PORT
    # POSTGRES_DB
    await db.connect()

    try:
        if args.command == "inspect":
            await inspect_dlq()

        elif args.command == "requeue":
            await requeue_event(args.event_id)

    finally:
        # Always close the PostgreSQL connection pool.
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

