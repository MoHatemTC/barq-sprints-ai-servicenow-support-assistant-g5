from pydantic import BaseModel, ConfigDict, Field

class IncidentPayload(BaseModel):
    sys_id: str = Field(..., min_length=32, max_length=32, pattern=r"^[0-9a-fA-F]{32}$", description="Unique 32-character ServiceNow Sys ID")
    number: str = Field(..., pattern=r"^INC\d+$", description="Incident number (e.g., INC0010001)")
    short_description: str = Field(..., min_length=1, max_length=4000, description="Short summary of the issue")
    description: str = Field(..., min_length=1, max_length=100000, description="Detailed description of the issue")

    model_config = ConfigDict(populate_by_name=True)