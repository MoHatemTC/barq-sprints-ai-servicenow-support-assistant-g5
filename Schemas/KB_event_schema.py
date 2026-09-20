from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import Any, Literal, Optional


class KB_event(BaseModel):
    """
    Pydantic schema for validating ServiceNow Knowledge Base (KB) events.
    """

    sys_id: str = Field(
        ...,
        description="ServiceNow unique identifier of the article"
    )

    article_id: str = Field(
        ...,
        description="Article Number, e.g., KB0010039"
    )

    version: Optional[str] = Field(
        None,
        description="Article Version"
    )

    short_description: str = Field(
        ...,
        description="Short description of the article"
    )

    author: Optional[str] = Field(
        None,
        description="Author of the article"
    )

    kb_category: Optional[str] = Field(
        None,
        description="Article category"
    )

    workflow_state: str = Field(
        ...,
        description="Workflow state of the article (published or retired)"
    )

    sys_updated_on: Optional[str] = Field(
        None,
        description="Last updated timestamp"
    )

    text: Optional[str] = Field(
        None,
        description="The content/body of the article"
    )

    operation: Literal["insert", "update", "delete", "retire"] = Field(
        ...,
        description="Operation that happened to the article"
    )

    @model_validator(mode="before")
    @classmethod
    def validation(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        unwrapped = {}

        for key, value in data.items():
            if isinstance(value, dict):
                if key == "sys_updated_on":
                    unwrapped[key] = (
                        value.get("value")
                        or value.get("display_value", "")
                    )
                else:
                    display_value = value.get("display_value")

                    unwrapped[key] = (
                        display_value
                        if display_value
                        else value.get("value", "")
                    )
            else:
                unwrapped[key] = value

        return unwrapped

    @field_validator("workflow_state", mode="before")
    @classmethod
    def validate_workflow_state(cls, value: Any) -> str:

        if isinstance(value, dict):
            value = (
                value.get("display_value")
                or value.get("value", "")
            )

        value = str(value).strip().lower()

        if value not in {"published", "retired"}:
            raise ValueError(
                f"Validation failed: Invalid workflow state '{value}'"
            )

        return value

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore"
    )