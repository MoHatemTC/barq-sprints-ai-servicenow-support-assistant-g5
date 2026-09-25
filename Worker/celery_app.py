import os
import asyncio

from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown
from dotenv import load_dotenv

from App.database import db

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")

if not REDIS_URL:
    raise RuntimeError("REDIS_URL is not set")


celery_app = Celery(
    "AI_Assisstant_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["Worker.tasks"],
)


celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=300,
    task_time_limit=360,
    broker_transport_options={
        "visibility_timeout": 420,
    },
)


@worker_process_init.connect
def init_worker_process(**kwargs):
    """
    Initialize a separate PostgreSQL connection pool
    for each Celery worker process.
    """
    asyncio.run(db.connect())


@worker_process_shutdown.connect
def shutdown_worker_process(**kwargs):
    """
    Close the PostgreSQL connection pool
    when a Celery worker process shuts down.
    """
    asyncio.run(db.disconnect())