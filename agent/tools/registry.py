"""Tool Registry for Sprint 3.3 Agent Tool Layer.

Exposes exactly four tools bound to an incident run context:
1. searchKB (Non-terminal)
2. addworknote (Non-terminal)
3. suggestAnswer (Terminal)
4. requestHR (Terminal)

Enforces strict security checks ensuring no capability exists to resolve,
close, or reassign incidents.
"""

from typing import Any, Callable, Dict, List, Optional
from langchain_core.tools import StructuredTool, tool

from agent.config import FORBIDDEN_TOOL_WORDS
from agent.ports import WriteBackPort
from agent.run_context import RunContext
from agent.tools.add_worknote import AddWorkNoteTool
from agent.tools.request_hr import RequestHRTool
from agent.tools.search_kb import SearchKBTool
from agent.tools.suggest_answer import SuggestAnswerTool

EXACT_TOOL_NAMES = {"searchKB", "addworknote", "suggestAnswer", "requestHR"}


class ToolRegistry:
    """Registry binding exactly four tools to a specific incident RunContext."""

    def __init__(
        self,
        run_context: RunContext,
        write_back_port: WriteBackPort,
        qdrant_service: Any,
        embedder: Any,
        score_threshold: Optional[float] = None,
        top_k: Optional[int] = None,
    ):
        self.run_context = run_context
        self.write_back_port = write_back_port
        self.qdrant_service = qdrant_service
        self.embedder = embedder

        # Instantiate the 4 bounded tools
        search_kwargs = {}
        if score_threshold is not None:
            search_kwargs["score_threshold"] = score_threshold
        if top_k is not None:
            search_kwargs["top_k"] = top_k

        self.search_kb_tool = SearchKBTool(
            run_context=self.run_context,
            qdrant_service=self.qdrant_service,
            embedder=self.embedder,
            **search_kwargs,
        )
        self.add_worknote_tool = AddWorkNoteTool(
            run_context=self.run_context,
            write_back_port=self.write_back_port,
        )
        self.suggest_answer_tool = SuggestAnswerTool(
            run_context=self.run_context,
            write_back_port=self.write_back_port,
        )
        self.request_hr_tool = RequestHRTool(
            run_context=self.run_context,
            write_back_port=self.write_back_port,
        )

        self._tools: Dict[str, Callable] = {
            "searchKB": self.search_kb_tool,
            "addworknote": self.add_worknote_tool,
            "suggestAnswer": self.suggest_answer_tool,
            "requestHR": self.request_hr_tool,
        }

        # Run safety validation on creation
        self.assert_strictly_four_tools()

    @property
    def tools(self) -> Dict[str, Callable]:
        """Return the dictionary of 4 bound tools."""
        return self._tools

    def assert_strictly_four_tools(self) -> None:
        """Validate that exactly four approved tools exist and no write-capable actions leak."""
        names = set(self._tools.keys())
        if names != EXACT_TOOL_NAMES:
            raise ValueError(
                f"Registry must expose exactly {EXACT_TOOL_NAMES}. Found: {names}"
            )

        if len(self._tools) != 4:
            raise ValueError(f"Expected exactly 4 tools, got {len(self._tools)}")

        # Tool name security check
        for name in names:
            for forbidden in FORBIDDEN_TOOL_WORDS:
                if forbidden in name.lower() and name not in EXACT_TOOL_NAMES:
                    raise RuntimeError(
                        f"Forbidden verb '{forbidden}' found in tool '{name}'. "
                        "Agent must remain read-only / advisory."
                    )

    def get_langchain_tools(self) -> List[StructuredTool]:
        """Convert bounded tools into LangChain StructuredTool instances for LLM agent integration."""
        lc_search = StructuredTool.from_function(
            func=self.search_kb_tool.run,
            name="searchKB",
            description=(
                "Non-terminal: Search published knowledge base articles in Qdrant vector database. "
                "Takes a search query and returns matching chunks above the confidence threshold."
            ),
        )

        lc_add_worknote = StructuredTool.from_function(
            func=self.add_worknote_tool.run,
            name="addworknote",
            description=(
                "Non-terminal: Add an internal work note to the ServiceNow incident. "
                "Takes note string (max 4000 characters) and posts it via the write-back port."
            ),
        )

        lc_suggest = StructuredTool.from_function(
            func=self.suggest_answer_tool.run,
            name="suggestAnswer",
            description=(
                "Terminal: Submit a suggested resolution for human review. "
                "Procedure must be a numbered list with inline citations [Article: KBxxxxxxx]. "
                "Locks the run context upon success."
            ),
        )

        lc_request_hr = StructuredTool.from_function(
            func=self.request_hr_tool.run,
            name="requestHR",
            description=(
                "Terminal: Escalate incident to a human service desk agent. "
                "Takes an escalation reason and locks the run context upon success."
            ),
        )

        tools = [lc_search, lc_add_worknote, lc_suggest, lc_request_hr]
        return tools
