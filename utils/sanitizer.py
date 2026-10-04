"""utils/sanitizer.py

Tier 1: Pre-Flight Deterministic Sanitizer.
Combines truncation, mathematical Shannon entropy detection (language-agnostic),
and multilingual credential masking (English + Arabic + universal formats).
"""

import math
import re
from collections import Counter

# 1. Truncation Guardrail
def truncate_text(text: str, max_chars: int = 4000) -> str:
    """Enforces character truncation to prevent context-window flooding."""
    if not text:
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + "\n... [SYSTEM WARNING: PAYLOAD TRUNCATED DUE TO SIZE LIMIT]"
    return text


# 2. Shannon Entropy (Language-Agnostic Password Detection)
def calculate_shannon_entropy(token: str) -> float:
    """Calculates mathematical entropy (randomness) of a token."""
    if not token:
        return 0.0
    entropy = 0.0
    length = len(token)
    counts = Counter(token)
    for count in counts.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy


def mask_high_entropy_tokens(text: str, entropy_threshold: float = 3.0, min_length: int = 7) -> str:
    """Masks tokens that look like passwords based on mathematical randomness,
    regardless of what language surrounds them (French, German, Arabic, etc.).
    """
    words = text.split()
    sanitized_words = []

    for word in words:
        # Skip tokens that are already redaction markers from earlier masking steps
        if "[REDACTED" in word:
            sanitized_words.append(word)
            continue

        # Skip tokens that look like error codes (e.g. AUTH-403, HTTP-500, 0x80040115)
        if re.match(r"^[A-Z]+-\d+$", word) or re.match(r"^0x[0-9A-Fa-f]+$", word):
            sanitized_words.append(word)
            continue

        # Strip trailing punctuation for the test
        clean_token = re.sub(r"[^\w@#$%^&*!_\-+=]", "", word)
        
        has_digits = bool(re.search(r"\d", clean_token))
        has_letters = bool(re.search(r"[a-zA-Z\u0600-\u06FF]", clean_token))
        has_special = bool(re.search(r"[@#$%^&*!_\-+=]", clean_token))
        
        is_mixed = (has_digits and has_letters) or (has_special and (has_digits or has_letters))

        # Passwords typically have: length >= 7, high entropy, and mixed character types
        if len(clean_token) >= min_length and is_mixed:
            if calculate_shannon_entropy(clean_token) >= entropy_threshold:
                sanitized_words.append("[REDACTED_CREDENTIAL]")
                continue

        sanitized_words.append(word)

    return " ".join(sanitized_words)


# 3. Multilingual Credential Keywords (English & Arabic)
CREDENTIAL_KEYWORDS = (
    r"password|passwd|pwd|pass|token|secret|pin|api[_-]?key|auth|"
    r"كلمة\s*السر|كلمة\s*المرور|الباسورد|باسورد|الرقم\s*السري|رمز\s*المرور|كود\s*الدخول"
)

# 3. Connectors handling multiple words (e.g. 'بتاعي هو', 'الخاص بي هو', 'is:', '=')
CREDENTIAL_CONNECTORS = (
    r"(?:\s*(?:is|was|هو|هي|بتاعي|بتاعتي|الخاص\s*بي|الخاصة\s*بي|عبارة\s*عن|كالتالي|[=:\-]))*"
)
CREDENTIAL_PATTERN = re.compile(
    rf"(?i)({CREDENTIAL_KEYWORDS})(?!-\d)(?:{CREDENTIAL_CONNECTORS})[\s:=]+([^\s,;]+)",
    re.UNICODE,
)

# Matches IPv4 and standard internal subnet IPs
IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?\b")

# Matches common API key prefixes (AWS, GitHub, OpenAI)
API_KEY_PATTERN = re.compile(r"\b(?:sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})\b")


def mask_pii_deterministic(text: str) -> str:
    """Tier 1 Pre-Flight Deterministic Sanitizer:
    Applies IP masking, credential regex (EN + AR), API keys, and Shannon entropy.
    """
    if not text:
        return ""

    # Step A: Mask IP addresses
    masked = IP_PATTERN.sub("[REDACTED_IP]", text)

    # Step B: Mask well-known API key tokens
    masked = API_KEY_PATTERN.sub("[REDACTED_API_KEY]", masked)

    # Step C: Mask explicit credential labels (English + Arabic)
    masked = CREDENTIAL_PATTERN.sub(r"\1: [REDACTED_CREDENTIAL]", masked)

    # Step D: Mask high-entropy strings (catches raw passwords with no label)
    masked = mask_high_entropy_tokens(masked)

    return masked


def mask_pii(text: str) -> str:
    """Master Masking Function:
    Applies local Qwen 2.5:3b model via Ollama for intelligent PII redaction (EN + AR),
    with automatic fallback to deterministic regex/entropy masking.
    """
    if not text:
        return ""

    # Pre-mask deterministic credentials/IPs first
    deterministic_masked = mask_pii_deterministic(text)

    # Apply Qwen 2.5:3b contextual PII masking
    try:
        from utils.ollama_masker import mask_pii_with_qwen
        return mask_pii_with_qwen(deterministic_masked)
    except Exception:
        return deterministic_masked