import re

def truncate_text(text: str, max_chars: int = 4000) -> str:
    """Enforces character truncation to prevent buffer overflows."""
    if not text:
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + "\n... [SYSTEM WARNING: PAYLOAD TRUNCATED DUE TO SIZE LIMIT]"
    #add this system warning to let LLM know that it was intentionally truncated and avoid model halicuination 
    return text

def mask_pii(text: str) -> str:
    """Uses Regex to redact sensitive infrastructure and user data."""
    if not text:
        return ""
        
    # Mask IPv4 Addresses
    ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
    masked_text = re.sub(ip_pattern, "[REDACTED_IP]", text)
    
    # Mask Passwords, Tokens, and API Keys
    credential_pattern = r'(?i)(password|pass|token|api_key|secret)[\s:=]+([A-Za-z0-9@#$%^&+=_-]+)'
    masked_text = re.sub(credential_pattern, r'\1: [REDACTED_CREDENTIAL]', masked_text)
    
    return masked_text