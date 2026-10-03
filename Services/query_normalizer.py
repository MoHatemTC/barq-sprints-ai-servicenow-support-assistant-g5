"""Services/query_normalizer.py

Tier 2 (In-Flight Semantic DLP) & Tier 3 (Post-Flight Validation Guardrail).
Translates noisy, colloquial, multilingual tickets into clean English technical search phrases.
"""

import logging
import re
from typing import List, Optional
from pydantic import BaseModel, Field

from Services.llm import get_llm
from utils.sanitizer import mask_pii

logger = logging.getLogger("servicenow.query_normalizer")

# Strip XML delimiters to prevent prompt boundary escaping
DELIMITER_RE = re.compile(r"<\s*/?\s*incident_data\s*>", re.IGNORECASE)


class NormalizedIncident(BaseModel):
    """Pydantic schema enforcing structured, injection-safe output."""

    affected_system: Optional[str] = Field(
        default=None,
        description="Software, hardware, or network service (e.g., 'Cisco AnyConnect', 'Outlook 365', 'Wi-Fi adapter').",
    )
    core_technical_symptom: str = Field(
        ...,
        description="Objective 3-7 word technical problem in English, with zero emotion, urgency, or personal context.",
    )
    detected_error_codes: List[str] = Field(
        default_factory=list,
        description="Any error codes or hex strings detected (e.g., 'AUTH-403', '0x80040115').",
    )
    urgency_sentiment: str = Field(
        default="neutral",
        description="Detected employee sentiment ('frustrated', 'urgent', 'neutral').",
    )
    optimized_search_query: str = Field(
        ...,
        description="Clean English search phrase combining system, error code, and symptom for knowledge base retrieval.",
    )


NORMALIZER_SYSTEM_PROMPT = """You are an enterprise IT Support Query Normalizer.
You will receive an employee support ticket in ANY language or dialect (English, Arabic, French, German, Spanish, Franco-Arab, etc.).

UNIVERSAL PRIVACY & CREDENTIAL DIRECTIVE:
1. NEVER output or repeat any passwords, PINs, secrets, API tokens, or IP addresses in your response.
2. If any token in the text functions as an authentication secret (a password the user entered, an access code, a private key):
   - Completely DISCARD that secret value.
   - Translate the issue into a generic English technical symptom (e.g., "account login password authentication failure").
3. Strip all emotional venting, anger, and urgency markers (e.g. 'URGENT', 'presentation in 5 min', 'boss is angry').
4. Strip all personal stories (spilled coffee, meetings, travel).
5. Always output the optimized_search_query in clean technical ENGLISH to match our knowledge base.
"""


def normalize_incident(raw_text: str) -> NormalizedIncident:
    """Orchestrates Tier 1 pre-masking, Tier 2 LLM semantic extraction, and Tier 3 post-scrubbing."""
    if not raw_text or not raw_text.strip():
        return NormalizedIncident(
            core_technical_symptom="unspecified issue",
            optimized_search_query="general IT troubleshooting",
        )

    # 1. Tier 1 Pre-Flight: Apply deterministic regex + entropy masking first
    pre_sanitized = mask_pii(raw_text)
    cleaned_input = DELIMITER_RE.sub(" ", pre_sanitized).strip()[:1500]

    try:
        # 2. Tier 2 In-Flight: Structured multilingual semantic extraction
        llm = get_llm()
        structured_llm = llm.with_structured_output(NormalizedIncident)

        prompt = (
            f"{NORMALIZER_SYSTEM_PROMPT}\n\n"
            f"<incident_data>\n{cleaned_input}\n</incident_data>\n\n"
            "Extract the objective technical search query."
        )

        result: NormalizedIncident = structured_llm.invoke(prompt)

        # 3. Tier 3 Post-Flight: Scrub output query to ensure no credentials leaked
        post_sanitized = mask_pii(result.optimized_search_query)
        clean_query = post_sanitized.replace("[REDACTED_CREDENTIAL]", "").replace("[REDACTED_IP]", "")
        
        # Clamp length to 120 chars as an injection-prevention guardrail
        result.optimized_search_query = " ".join(clean_query.split())[:120].strip()

        logger.info(
            "Normalized query: '%s' (System: %s, Error: %s)",
            result.optimized_search_query,
            result.affected_system,
            result.detected_error_codes,
        )
        return result

    except Exception as exc:
        logger.warning("Normalizer LLM failed (%s). Falling back to Tier 1 sanitized text.", exc)
        fallback_query = " ".join(cleaned_input.split()[:12])
        return NormalizedIncident(
            core_technical_symptom=fallback_query,
            optimized_search_query=fallback_query,
        )