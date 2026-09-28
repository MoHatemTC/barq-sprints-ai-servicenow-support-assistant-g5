"""LLM access through the Sprints LiteLLM proxy (OpenAI-compatible API)."""

import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


@lru_cache(maxsize=1)
def get_llm() -> ChatOpenAI:
    base_url = os.getenv("LITELLM_BASE_URL")
    api_key = os.getenv("LITELLM_API_KEY")
    if not base_url or not api_key:
        raise RuntimeError("LITELLM_BASE_URL and LITELLM_API_KEY must be set in .env")

    return ChatOpenAI(
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        model=os.getenv("LLM_MODEL", "gemini-2.5-flash"),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0")),  # low by default: deterministic agent
        timeout=30,
        max_retries=1,
    )