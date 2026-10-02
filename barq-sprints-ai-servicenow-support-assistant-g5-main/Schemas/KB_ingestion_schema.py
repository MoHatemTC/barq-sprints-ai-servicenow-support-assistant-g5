from pydantic import BaseModel, Field


class KBIngestionPayload(BaseModel):
    """
    Payload contract for KB vector ingestion/upsert.
    """

    article_id: str = Field(
        ...,
        description="Unique identifier of the KB article"
    )

    title: str = Field(
        ...,
        description="Title of the KB article"
    )

    text: str = Field(
        ...,
        description="Full text/content of the KB article"
    )

    workflow_state: str = Field(
        ...,
        description="Current workflow state of the article"
    )

    category: str = Field(
        ...,
        description="KB article category"
    )