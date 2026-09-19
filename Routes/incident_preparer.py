import re
from typing import List
from pydantic import BaseModel
from incidentContext import IncidentContext
# 2. The Processing Class
class IncidentContextPreparer:
    def __init__(self, max_chars: int = 4000):
        # We use characters for truncation here as a lightweight proxy for tokens (approx 1000 tokens)
        self.max_chars = max_chars
        
        # Basic stop words to ignore when extracting search tags
        self.stop_words = {"the", "is", "at", "which", "on", "and", "a", "an", "of", "to", "in", "it", "for", "with", "my", "i", "doesn't", "cant", "cannot"}

    def process_payload(self, sys_id: str, number: str, short_desc: str, desc: str) -> IncidentContext:
        """Main pipeline that runs all sanitization steps in order."""
        
        # Step A: Truncate oversized descriptions
        safe_desc = self._truncate_text(desc)
        
        # Step B: Mask PII (Passwords, IPs, etc.)
        combined_text = f"{short_desc}\n{safe_desc}"
        masked_text = self._mask_pii(combined_text)
        
        # Step C: Extract tags for future Vector DB
        tags = self._extract_tags(short_desc)
        
        # Step D: Apply prompt injection defenses (XML wrapping)
        final_query = self._defend_injection(masked_text)
        
        # Return the validated Pydantic object
        return IncidentContext(
            sys_id=sys_id,
            original_number=number,
            sanitized_query=final_query,
            truncated_description=safe_desc,
            extracted_tags=tags,
            is_safe=True # We will add logic to flag this False if severe anomalies are found
        )