import os

from celery import Celery
from dotenv import load_dotenv

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

