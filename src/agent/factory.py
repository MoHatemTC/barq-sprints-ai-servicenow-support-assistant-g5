"""One place that builds the agent's tools for a run (S3.3 tools + S3.4 loop).

Every caller (pipeline, Celery handler, scripts) uses this, so swapping the
write-back port (fake -> ServiceNow) is a one-line change here.
"""

from agent.ports import WriteBackPort
from agent.run_context import RunContext
from agent.tools.registry import ToolRegistry
from Services.shared import get_embedder, get_qdrant
from src.writeback.agent_adapter import ServiceNowWritebackAdapter


def get_write_back_port() -> WriteBackPort:
    """Write-back target for suggestAnswer / requestHR / addworknote."""
    return ServiceNowWritebackAdapter()


def new_run_context(sys_id: str, number: str) -> RunContext:
    return RunContext(sys_id=sys_id, number=number)


def build_agent_tools(
    run_ctx: RunContext,
    write_back_port: WriteBackPort | None = None,
) -> list:
    """Exactly four LangChain tools bound to this run: searchKB, addworknote, suggestAnswer, requestHR."""
    registry = ToolRegistry(
        run_context=run_ctx,
        write_back_port=write_back_port or get_write_back_port(),
        qdrant_service=get_qdrant(),
        embedder=get_embedder(),
    )
    return registry.get_langchain_tools()