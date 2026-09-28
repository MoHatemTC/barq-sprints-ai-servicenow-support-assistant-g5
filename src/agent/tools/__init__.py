"""src.agent.tools forwarding to Agent.tools."""

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
