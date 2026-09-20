# utils/security.py
import re
from typing import Tuple

INJECTION_KEYWORDS = [
    "ignore previous", "forget previous", "system prompt",
    "instructions", "bypass", "override", "you are now", "disregard"
]

def secure_payload(text: str) -> Tuple[str, bool]:
    """
    Neutralizes injection attempts by stripping brackets and wrapping in strict XML tags.
    Returns the wrapped text and an is_safe boolean flag.
    """
    if not text:
        return "<incident_data></incident_data>", True

    is_safe = True
    lower_text = text.lower()
    
    # 1. Flag severe anomalies if hacker keywords are detected
    if any(keyword in lower_text for keyword in INJECTION_KEYWORDS):
        is_safe = False

    # 2. Strip out angle brackets to prevent delimiter escape
    safe_text = re.sub(r'<[^>]+>', '', text)

    # 3. Wrap in strict data delimiters
    wrapped_query = f"<incident_data>\n{safe_text.strip()}\n</incident_data>"

    return wrapped_query, is_safe