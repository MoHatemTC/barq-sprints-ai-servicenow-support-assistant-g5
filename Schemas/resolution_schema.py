from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResolvedIncidentPayload(BaseModel):
    sys_id: str = Field(
        ...,
        min_length=32,
        max_length=32,
        pattern=r"^[0-9a-fA-F]{32}$",
        description="Unique 32-character ServiceNow Sys ID",
    )
    number: Optional[str] = Field(None, description="Incident number (e.g., INC0010291)")
    short_description: Optional[str] = Field("", description="Short summary of the issue")
    description: Optional[str] = Field("", description="Detailed description of the issue")
    close_code: str = Field(..., description="ServiceNow close code")
    close_notes: str = Field(..., description="Human resolution notes")
    resolved_by: Optional[str] = Field(None, description="User who resolved the incident")
    resolved_at: Optional[str] = Field(None, description="Timestamp when incident was resolved")
    ai_confidence: Optional[float] = Field(None, description="AI confidence score if available")
    ai_suggested_response: Optional[str] = Field(None, description="AI suggested response if available")

    @field_validator("close_notes")
    @classmethod
    def validate_close_notes_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("close_notes must be non-empty.")
        return v

    model_config = ConfigDict(populate_by_name=True)
