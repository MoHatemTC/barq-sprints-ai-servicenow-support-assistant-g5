from pydantic import BaseModel, Field

class IncidentEventPayload(BaseModel):
    event_id: str = Field(..., description="Unique identifier for the emitted event")
    sys_id: str = Field(..., description="ServiceNow sys_id of the incident")
    number: str = Field(..., description="Incident ticket number (e.g., INC0001234)")
    event_type: str = Field(..., description="Type of the event triggering the webhook")

    class Config:
        populate_by_name = True