import re
from typing import List
from pydantic import BaseModel

# 1. The Output Schema (What this module hands back to FastAPI)
class IncidentContext(BaseModel):
    sys_id: str
    original_number: str
    sanitized_query: str
    truncated_description: str
    extracted_tags: List[str]
    is_safe: bool