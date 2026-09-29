from pydantic import BaseModel, Field
from typing import Optional, List

class NormalizedIncident(BaseModel):
    """Clean technical representation of an employee ticket."""
    
    affected_system: Optional[str] = Field(
        default=None,
        description="The software, hardware, or network service (e.g. 'Cisco AnyConnect', 'Outlook 365', 'GlobalProtect')."
    )
    
    core_technical_symptom: str = Field(
        ...,
        description="Objective 3-7 word technical failure, stripped of all emotion, anger, or personal stories."
    )
    
    detected_error_codes: List[str] = Field(
        default_factory=list,
        description="Any error codes or hex strings detected (e.g., '0x80070005', 'HTTP 403', 'STATUS_ACCESS_DENIED')."
    )
    
    urgency_sentiment: str = Field(
        default="neutral",
        description="Employee tone ('frustrated', 'urgent', 'neutral'). Used for ticket triage, but STRIPPED from search query."
    )
    
    optimized_search_query: str = Field(
        ...,
        description="The optimal search phrase combining system, error code, and symptom for dense vector retrieval in Qdrant."
    )