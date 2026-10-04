"""utils/ollama_masker.py

Data Masking & PII Sanitization module powered by Ollama Qwen 2.5:3b local LLM.

Features:
- Multilingual PII detection (Arabic + English).
- Redacts Names, Emails, Phone Numbers, Passwords, API Keys, Credit Cards, and SSN/National IDs.
- Preserves technical incident descriptions, error codes, logs, and ServiceNow ticket metadata.
- Automatic fallback to deterministic regex/entropy masking if Ollama is unreachable or times out.
"""

import logging
import os
import re
from typing import Optional
import httpx

logger = logging.getLogger("servicenow_support.ollama_masker")

OLLAMA_MODEL = os.getenv("OLLAMA_MASKING_MODEL", "qwen2.5:3b")
OLLAMA_BASE_URLS = [
    os.getenv("OLLAMA_BASE_URL"),
    "http://localhost:11434",
    "http://host.docker.internal:11434",
    "http://172.17.0.1:11434",
]
OLLAMA_BASE_URLS = [u for u in OLLAMA_BASE_URLS if u]

MASKING_SYSTEM_PROMPT = """You are a strict, privacy-preserving Data Masking Assistant for a ServiceNow Support System.
Your ONLY job is to identify and mask sensitive personal and security information (PII) from the user input text in both ARABIC and ENGLISH.

REDACTION RULES:
1. Replace Personal Names (Arabic or English names of employees/users) with `[REDACTED_NAME]`
2. Replace Phone Numbers (mobile, landline, WhatsApp numbers) with `[REDACTED_PHONE]`
3. Replace Email Addresses with `[REDACTED_EMAIL]`
4. Replace Passwords, Secrets, API Keys, Passphrases with `[REDACTED_CREDENTIAL]`
5. Replace Credit Card numbers, IBANs, SSN, National IDs with `[REDACTED_SENSITIVE]`
6. Replace IP Addresses with `[REDACTED_IP]`

STRICT CONSTRAINTS:
- Keep all technical terms, error logs, incident IDs, software names, and non-sensitive sentence structure UNCHANGED.
- Do NOT answer the incident, do NOT add greetings, explanations, or commentary.
- Return ONLY the exact original text with sensitive entities replaced by redaction tags.
"""


class OllamaMasker:
    """Masker utilizing local Qwen 2.5:3b model via Ollama API."""

    def __init__(self, model_name: str = OLLAMA_MODEL, timeout_seconds: float = 30.0):
        self.model_name = model_name
        self.timeout_seconds = float(os.getenv("OLLAMA_TIMEOUT", str(timeout_seconds)))
        self.active_base_url: Optional[str] = None

    def _find_active_url(self) -> Optional[str]:
        if self.active_base_url:
            return self.active_base_url

        for url in OLLAMA_BASE_URLS:
            try:
                endpoint = f"{url.rstrip('/')}/api/tags"
                resp = httpx.get(endpoint, timeout=1.5)
                if resp.status_code == 200:
                    self.active_base_url = url.rstrip('/')
                    logger.info(f"Connected to Ollama at {self.active_base_url}")
                    return self.active_base_url
            except Exception:
                continue
        return None

    def mask_text_with_ollama(self, text: str) -> Optional[str]:
        """Send text to Qwen 2.5:3b model on Ollama for intelligent PII redaction."""
        if not text or not text.strip():
            return text

        base_url = self._find_active_url()
        if not base_url:
            logger.warning("Ollama API unreachable. Falling back to deterministic masking.")
            return None

        endpoint = f"{base_url}/api/chat"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": MASKING_SYSTEM_PROMPT},
                {"role": "user", "content": f"Mask all PII in this text:\n\n{text}"}
            ],
            "stream": False,
            "options": {
                "temperature": 0.0,
                "top_p": 0.1,
            }
        }

        try:
            resp = httpx.post(endpoint, json=payload, timeout=self.timeout_seconds)
            if resp.status_code == 200:
                result_json = resp.json()
                masked_output = result_json.get("message", {}).get("content", "").strip()
                if masked_output:
                    # Clean any unwanted markdown fences wrapping the response
                    clean_output = re.sub(r"^```[a-z]*\n|\n```$", "", masked_output, flags=re.MULTILINE).strip()
                    return clean_output
            logger.warning(f"Ollama returned status {resp.status_code}: {resp.text}")
        except Exception as exc:
            logger.warning(f"Ollama masking failed ({type(exc).__name__}: {exc}). Falling back to regex.")

        return None


# Global singleton instance
_masker_instance: Optional[OllamaMasker] = None


def get_ollama_masker() -> OllamaMasker:
    global _masker_instance
    if _masker_instance is None:
        _masker_instance = OllamaMasker()
    return _masker_instance


def mask_pii_with_qwen(text: str) -> str:
    """Master masking function combining Ollama Qwen 2.5:3b with deterministic fallback."""
    if not text or not text.strip():
        return text

    masker = get_ollama_masker()
    ollama_masked = masker.mask_text_with_ollama(text)

    if ollama_masked:
        return ollama_masked

    # Fallback to deterministic regex + entropy masking if Ollama call was not successful
    from utils.sanitizer import mask_pii_deterministic
    return mask_pii_deterministic(text)
