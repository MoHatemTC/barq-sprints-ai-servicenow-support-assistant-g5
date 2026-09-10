from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, Any

class ServiceNowKBArticle(BaseModel):
    """
    Pydantic schema for validating ServiceNow Knowledge Base (KB) articles.
    """
    number: str = Field(..., description="Article Number, e.g., KB0010039")
    version: Optional[str] = Field(None, description="Article Version")
    short_description: str = Field(..., description="Short description of the article")
    author: Optional[str] = Field(None, description="Author of the article")
    category: Optional[str] = Field(None, description="Article category")
    workflow_state: str = Field(..., description="Workflow state of the article (must be published)")
    sys_updated_on: Optional[str] = Field(None, description="Last updated timestamp")
    
    # Optional fields that might be useful from the KB body
    text: Optional[str] = Field(None, description="The content/body of the article")

    @field_validator('version', 'author', 'category', mode='before')
    @classmethod
    def extract_reference_value(cls, value: Any) -> Optional[str]:
        """
        ServiceNow often returns reference fields as a dictionary: {'link': '...', 'value': '...'}
        This extracts the value.
        """
        if isinstance(value, dict):
            return value.get('value', '')
        return str(value) if value is not None else None

    @field_validator('workflow_state', mode='before')
    @classmethod
    def ensure_published(cls, value: Any) -> str:
        """
        Validates that the retrieved article is in the 'published' state.
        Raises a ValueError if the article is not published.
        """
        # Handle if workflow_state is a reference dict
        if isinstance(value, dict):
            value = value.get('value', '')
            
        if not value or str(value).strip().lower() != 'published':
            raise ValueError(f"Validation failed: Only published articles are allowed. Received state: '{value}'")
        return str(value).strip().lower()

    model_config = ConfigDict(
        populate_by_name=True,
        extra='ignore' # Ignores any other fields returned by the ServiceNow API
    )
