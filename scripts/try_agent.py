"""Manual check of the ReAct loop against the real LLM + Qdrant.

    python -m scripts.try_agent "wifi keeps disconnecting on my laptop"
"""
import json
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from agent.agent import get_knowledge_retriever
from src.agent.local_tools import build_local_tools
from src.agent.react_agent import AgentConfig, run_agent
from src.agent.run_context import RunContext
from Services.incident_preparer import IncidentContextPreparer


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    text = " ".join(sys.argv[1:]) or "wifi keeps disconnecting on my laptop"
    incident = IncidentContextPreparer().process_payload("0" * 32, "INC0000000", text, "")

    # NOTE: the webhook blocks is_safe=False payloads before the agent runs.
    # Here we run the agent anyway, to test the prompt's own injection defence.
    print("is_safe :", incident.is_safe, "| config:", AgentConfig.from_env())

    ctx = RunContext(incident.sys_id, incident.original_number)
    tools = build_local_tools(ctx, get_knowledge_retriever())
    result = run_agent(incident.sys_id, incident, tools, ctx=ctx)

    for e in result.events:
        print(json.dumps(e, ensure_ascii=False, default=str)[:600])
    print("\nOUTCOME :", result.outcome, "| iterations:", result.iterations,
          "| fallback:", result.fallback_reason)
    print("SOURCES :", result.sources, "| max_score:", result.max_score,
          "| prompt:", result.prompt_version, "| tokens:", result.total_tokens)
    print(result.procedure or result.reason)


if __name__ == "__main__":
    main()
