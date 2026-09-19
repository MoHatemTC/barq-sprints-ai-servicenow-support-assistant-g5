# input_processor.py
from schemas.Incident_context import IncidentContext
from utils.sanitizer import truncate_text, mask_pii
from utils.tag_extract import extract_tags
from utils.prompt_injection import secure_payload

class IncidentContextPreparer:
    def __init__(self, max_chars: int = 4000):
        self.max_chars = max_chars

    def process_payload(self, sys_id: str, number: str, short_desc: str, desc: str) -> IncidentContext:
        """Main pipeline orchestrator for Sprint 2 payload sanitization."""
        
        # 1. Truncate oversized descriptions
        safe_desc = truncate_text(desc, self.max_chars)
        
        # 2. Combine and Mask PII
        combined_text = f"{short_desc}\n{safe_desc}"
        masked_text = mask_pii(combined_text)
        
        # 3. Extract Tags (we mainly use short_desc as it's usually the most concise summary)
        tags = extract_tags(short_desc)
        
        # 4. Defend against Prompt Injection
        final_query, is_safe_flag = secure_payload(masked_text)
        
        # 5. Return the validated Pydantic object
        return IncidentContext(
            sys_id=sys_id,
            original_number=number,
            sanitized_query=final_query,
            truncated_description=safe_desc,
            extracted_tags=tags,
            is_safe=is_safe_flag
        )