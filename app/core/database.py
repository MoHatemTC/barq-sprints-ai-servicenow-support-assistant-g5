import os
import asyncpg
import logging
import asyncio

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
                new_pool = await asyncpg.create_pool(dsn=database_url, min_size=1, max_size=10)
                await self.init_db(new_pool)
                self.pool = new_pool
                logger.info("Database connection pool established.")
                break
            except Exception as e:
                if new_pool:
                    await new_pool.close()
                self.pool = None
                logger.warning(f"Database connection attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    logger.error("Max retries reached. Could not connect to database.")
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
        
        # Create the events_log table if it doesn't exist
        create_table_query = """
        CREATE TABLE IF NOT EXISTS events_log (
            event_id VARCHAR(255) PRIMARY KEY,
            status VARCHAR(50) NOT NULL,
            processed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
        async with pool.acquire() as conn:
            await conn.execute(create_table_query)
            logger.info("Checked/Initialized events_log table in database.")

    async def record_event(self, event_id: str, status: str = "processing") -> bool:
        """
        Attempts to record an event.
        Returns True if successfully inserted, False if it is a duplicate.
        """
        try:
            if not self.pool:
                raise RuntimeError("Database connection pool is not initialized.")
            async with self.pool.acquire() as conn:
                retention_seconds = int(os.getenv("IDEMPOTENCY_RETENTION_WINDOW", "0"))
                if retention_seconds > 0:
                    await conn.execute(
                        "DELETE FROM events_log WHERE processed_at < CURRENT_TIMESTAMP - ($1 * INTERVAL '1 second')",
                        retention_seconds,
                    )
                await conn.execute(
                    "INSERT INTO events_log (event_id, status) VALUES ($1, $2)",
                    event_id,
                    status
                )
                return True
        except asyncpg.exceptions.UniqueViolationError:
            return False
        except Exception as e:
            logger.error(f"Error recording event {event_id}: {e}")
            raise e

    async def update_event_status(self, event_id: str, status: str) -> None:
        if not self.pool:
            raise RuntimeError("Database connection pool is not initialized.")
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE events_log SET status = $2, processed_at = CURRENT_TIMESTAMP WHERE event_id = $1",
                event_id,
                status,
            )

db = Database()
