"""Tools module exposing the four Sprint 3.3 tools and ToolRegistry."""

from agent.tools.add_worknote import AddWorkNoteTool
from agent.tools.registry import ToolRegistry
from agent.tools.request_hr import RequestHRTool
from agent.tools.search_kb import SearchKBTool
from agent.tools.suggest_answer import SuggestAnswerTool

__all__ = [
    "SearchKBTool",
    "AddWorkNoteTool",
    "SuggestAnswerTool",
    "RequestHRTool",
    "ToolRegistry",
]
