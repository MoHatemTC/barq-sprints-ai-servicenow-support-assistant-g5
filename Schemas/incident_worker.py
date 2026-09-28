from datetime import datetime

from pydantic import BaseModel


class WorkerPayload(BaseModel):
    event_id: str
    sys_id: str
    number: str
    received_at: datetime