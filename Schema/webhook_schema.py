from pydantic import BaseModel, Field

class IncidentPayload(BaseModel):
    sys_id: str = Field(..., description="Unique 32-character ServiceNow Sys ID")
    number: str = Field(..., description="Incident number (e.g., INC0010001)")
    short_description: str = Field(..., description="Short summary of the issue")
    description: str = Field(..., description="Detailed description of the issue")

    class Config:
        populate_by_name = True