"""Tools module exposing the four Sprint 3.3 tools and ToolRegistry."""

from Agent.tools.add_worknote import AddWorkNoteTool
from Agent.tools.registry import ToolRegistry
from Agent.tools.request_hr import RequestHRTool
from Agent.tools.search_kb import SearchKBTool
from Agent.tools.suggest_answer import SuggestAnswerTool

__all__ = [
    "SearchKBTool",
    "AddWorkNoteTool",
    "SuggestAnswerTool",
    "RequestHRTool",
    "ToolRegistry",
]
