from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import Optional, Any

class ServiceNowKBArticle(BaseModel):
    """
    Pydantic schema for validating ServiceNow Knowledge Base (KB) articles.
    """
    number: str = Field(..., description="Article Number, e.g., KB0010039")
    version: Optional[str] = Field(None, description="Article Version")
    short_description: str = Field(..., description="Short description of the article")
    author: Optional[str] = Field(None, description="Author of the article")
    kb_category: Optional[str] = Field(None, description="Article category")
    workflow_state: str = Field(..., description="Workflow state of the article (must be published)")
    sys_updated_on: Optional[str] = Field(None, description="Last updated timestamp")
    
    # Optional fields that might be useful from the KB body
    text: Optional[str] = Field(None, description="The content/body of the article")

    @model_validator(mode='before')
    @classmethod
    def unwrap_display_values(cls, data: Any) -> Any:
        """
        With sysparm_display_value=all, ServiceNow wraps EVERY field as
        {'display_value': 'X', 'value': 'Y', 'link': '...'}, This runs before
        any field-level validation and unwraps every dict-shaped value in
        the raw payload.

        Prefer display_value (human-readable); fall back to value if
        display_value is missing/empty, so nothing silently becomes None.
        """
        if not isinstance(data, dict):
            return data

        unwrapped = {}
        for key, value in data.items():
            if isinstance(value, dict):
                if key == 'sys_updated_on':
                    unwrapped[key] = value.get('value') or value.get('display_value', '')
                else:
                    display_value = value.get('display_value')
                    unwrapped[key] = display_value if display_value else value.get('value', '')
            else:
                unwrapped[key] = value
        return unwrapped

    @field_validator('workflow_state', mode='before')
    @classmethod
    def ensure_published(cls, value: Any) -> str:
        """
        Validates that the retrieved article is in the 'published' state.
        Raises a ValueError if the article is not published.
        """
        # Handle if workflow_state is a reference dict
        if isinstance(value, dict):
            value = value.get('display_value') or value.get('value', '')
            
        if not value or str(value).strip().lower() != 'published':
            raise ValueError(f"Validation failed: Only published articles are allowed. Received state: '{value}'")
        return str(value).strip().lower()

    model_config = ConfigDict(
        populate_by_name=True,
        extra='ignore' # Ignores any other fields returned by the ServiceNow API
    )
