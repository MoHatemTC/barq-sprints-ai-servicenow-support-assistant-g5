import os
import asyncpg
import logging
import asyncio
from datetime import datetime


logger = logging.getLogger("servicenow_webhook.database")


class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        database_url = os.getenv("DATABASE_URL")

        if not database_url:
            database_url = (
                f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
                f"@{os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5432')}"
                f"/{os.getenv('POSTGRES_DB', 'servicenow_ai')}"
            )

        max_retries = 5

        for attempt in range(1, max_retries + 1):
            new_pool = None

            try:
                new_pool = await asyncpg.create_pool(
                    dsn=database_url,
                    min_size=1,
                    max_size=10,
                )

                await self.init_db(new_pool)

                self.pool = new_pool

                logger.info("Database connection pool established.")
                break

            except Exception as e:
                if new_pool:
                    await new_pool.close()

                self.pool = None

                logger.warning(
                    f"Database connection attempt {attempt} failed: {e}"
                )

                if attempt == max_retries:
                    logger.error(
                        "Max retries reached. Could not connect to database."
                    )
                    raise e

                await asyncio.sleep(2)

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed.")

    async def init_db(self, pool=None):
        pool = pool or self.pool

        if not pool:
            return

        create_table_query = """
        CREATE TABLE IF NOT EXISTS events_log (
            event_id VARCHAR(255) PRIMARY KEY,
            sys_id VARCHAR(255) NOT NULL,
            number VARCHAR(255) NOT NULL,
            status VARCHAR(50) NOT NULL,
            received_at TIMESTAMP WITH TIME ZONE NOT NULL,
            processed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (sys_id)
        );
        """

        create_completed_events_query = """
        CREATE TABLE IF NOT EXISTS completed_events (
            event_id VARCHAR(255) PRIMARY KEY,
            completed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """

        # DLQ:
        # Stores events that failed permanently or exhausted all retry attempts.
        # The payload is kept so the event can be inspected or requeued later.
        create_dead_letter_events_query = """
        CREATE TABLE IF NOT EXISTS dead_letter_events (
            event_id VARCHAR(255) PRIMARY KEY,
            payload JSONB NOT NULL,
            error TEXT NOT NULL,
            attempts INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """

        async with pool.acquire() as conn:
            await conn.execute(create_table_query)

            await conn.execute(create_completed_events_query)

            await conn.execute(create_dead_letter_events_query)

            logger.info(
                "Checked/Initialized events_log table in database."
            )

            logger.info(
                "Checked/Initialized completed_events table in database."
            )

            logger.info(
                "Checked/Initialized dead_letter_events table in database."
            )

    async def record_event(
        self,
        event_id: str,
        sys_id: str,
        number: str,
        received_at: datetime,
        status: str = "processing",
    ) -> bool:
        """
        Attempts to record an event.
        Returns True if successfully inserted, False if it is a duplicate.
        """

        try:
            if not self.pool:
                raise RuntimeError(
                    "Database connection pool is not initialized."
                )

            async with self.pool.acquire() as conn:

                retention_seconds = int(
                    os.getenv(
                        "IDEMPOTENCY_RETENTION_WINDOW",
                        "0",
                    )
                )

                if retention_seconds > 0:
                    await conn.execute(
                        """
                        DELETE FROM events_log
                        WHERE processed_at < CURRENT_TIMESTAMP
                        - ($1 * INTERVAL '1 second')
                        """,
                        retention_seconds,
                    )

                await conn.execute(
                    """
                    INSERT INTO events_log
                    (event_id, sys_id, number, received_at, status)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    event_id,
                    sys_id,
                    number,
                    received_at,
                    status,
                )

                return True

        except asyncpg.exceptions.UniqueViolationError:
            return False

        except Exception as e:
            logger.error(
                f"Error recording event {event_id}: {e}"
            )
            raise

    async def update_event_status(
        self,
        event_id: str,
        status: str,
    ) -> None:

        if not self.pool:
            raise RuntimeError(
                "Database connection pool is not initialized."
            )

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE events_log
                SET status = $2,
                    processed_at = CURRENT_TIMESTAMP
                WHERE event_id = $1
                """,
                event_id,
                status,
            )

    async def is_event_completed(self, event_id: str) -> bool:
        if not self.pool:
            raise RuntimeError(
                "Database connection pool is not initialized."
            )

        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                """
                SELECT 1
                FROM completed_events
                WHERE event_id = $1
                """,
                event_id,
            )

            return result is not None

    async def mark_event_completed(self, event_id: str) -> bool:
        if not self.pool:
            raise RuntimeError(
                "Database connection pool is not initialized."
            )

        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                INSERT INTO completed_events (event_id)
                VALUES ($1)
                ON CONFLICT (event_id) DO NOTHING
                """,
                event_id,
            )

            return result == "INSERT 0 1"
        
    # DLQ:
    # Permanently stores an event that cannot be processed successfully.
    # The payload is stored so the event can be inspected or requeued later.
    async def save_dead_letter(
        self,
        event_id: str,
        payload: dict,
        error: str,
        attempts: int,
    ) -> None:

        if not self.pool:
            raise RuntimeError(
                "Database connection pool is not initialized."
            )

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO dead_letter_events (
                    event_id,
                    payload,
                    error,
                    attempts
                )
                VALUES ($1, $2::jsonb, $3, $4)
                ON CONFLICT (event_id)
                DO UPDATE SET
                    payload = EXCLUDED.payload,
                    error = EXCLUDED.error,
                    attempts = EXCLUDED.attempts,
                    updated_at = CURRENT_TIMESTAMP
                """,
                event_id,
                __import__("json").dumps(payload),
                error,
                attempts,
            )

        logger.error(
            "Event moved to DLQ",
            extra={
                "event_id": event_id,
                "attempts": attempts,
                "outcome": "dead_lettered",
            },
        )


db = Database()

