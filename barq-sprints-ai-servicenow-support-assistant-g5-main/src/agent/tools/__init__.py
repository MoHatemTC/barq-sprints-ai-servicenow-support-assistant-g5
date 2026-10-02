"""src.agent.tools compatibility re-export for the canonical Agent tools package."""

from Agent.tools import (
    AddWorkNoteTool,
    RequestHRTool,
    SearchKBTool,
    SuggestAnswerTool,
    ToolRegistry,
)

__all__ = [
    "SearchKBTool",
    "AddWorkNoteTool",
    "SuggestAnswerTool",
    "RequestHRTool",
    "ToolRegistry",
]
