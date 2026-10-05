import os
from celery.signals import worker_process_init
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
celery_app.conf.worker_proc_alive_timeout = 180

celery_app.conf.update(
    task_acks_late=True,
    
    task_reject_on_worker_lost=True,
    
    worker_prefetch_multiplier=1,
    
    task_soft_time_limit=120,
    
    task_time_limit=150,
    
    broker_transport_options={
        "visibility_timeout": 120,
    },
)

@worker_process_init.connect
def preload_models(**_):
    from Services.shared import get_embedder, get_qdrant

    get_embedder().embed_text("warm up")
    get_qdrant()