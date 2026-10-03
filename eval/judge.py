"""LLM judge for DeepEval, pointed at the team's LiteLLM proxy.

Model name, base URL and API key come ONLY from environment variables
(the variable names are listed in eval/config.yaml).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any

from deepeval.models import DeepEvalBaseLLM


def _extract_json(text: str) -> Any:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in judge reply")
    return json.loads(text[start : end + 1])


class ProxyJudge(DeepEvalBaseLLM):
    def __init__(self, model: str, base_url: str, api_key: str, temperature: float = 0.0, retries: int = 3):
        # must be set BEFORE super().__init__, which calls load_model()
        self.model_name = model
        self._base_url, self._api_key = base_url, api_key
        self._temperature, self._retries = temperature, retries
        super().__init__(model)

    def load_model(self):
        from openai import OpenAI

        return OpenAI(base_url=self._base_url, api_key=self._api_key, timeout=120)

    def get_model_name(self) -> str:
        return self.model_name

    def _complete(self, prompt: str) -> str:
        resp = self.model.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=self._temperature,
        )
        return resp.choices[0].message.content or ""

    def generate(self, prompt: str, schema=None, **_: Any):
        if schema is not None:
            prompt += (
                "\n\nReturn ONLY one JSON object that conforms to this JSON schema. "
                "No prose, no code fences.\n" + json.dumps(schema.model_json_schema())
            )
        last: Exception | None = None
        for attempt in range(self._retries):
            try:
                text = self._complete(prompt)
                return text if schema is None else schema.model_validate(_extract_json(text))
            except Exception as exc:  # rate limit, bad JSON, network blip
                last = exc
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"judge failed after {self._retries} attempts: {type(last).__name__}: {last}")

    async def a_generate(self, prompt: str, schema=None, **kw: Any):
        return await asyncio.to_thread(self.generate, prompt, schema)


def build_judge(cfg: dict) -> ProxyJudge:
    j = cfg["judge"]
    model = os.getenv(j["model_env"]) or os.getenv(j["fallback_model_env"])
    base_url, api_key = os.getenv(j["base_url_env"]), os.getenv(j["api_key_env"])
    missing = [n for n, v in {j["model_env"] + " or " + j["fallback_model_env"]: model,
                              j["base_url_env"]: base_url, j["api_key_env"]: api_key}.items() if not v]
    if missing:
        raise SystemExit(f"Judge is not configured. Set these environment variables: {', '.join(missing)}")
    return ProxyJudge(model, base_url, api_key, temperature=float(j.get("temperature", 0)))