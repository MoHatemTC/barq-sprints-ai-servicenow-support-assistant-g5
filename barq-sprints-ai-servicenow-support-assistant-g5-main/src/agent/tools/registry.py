"""src.agent.tools.registry compatibility re-export for the canonical Agent tool registry."""

from Agent.tools.registry import EXACT_TOOL_NAMES, ToolRegistry

__all__ = ["ToolRegistry", "EXACT_TOOL_NAMES"]
