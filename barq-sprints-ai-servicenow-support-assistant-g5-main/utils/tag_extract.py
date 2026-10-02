import re
from typing import List

# A lightweight set of common filler words to ignore
STOP_WORDS = {
    "the", "is", "at", "which", "on", "and", "a", "an", "of", "to", "in", 
    "it", "for", "with", "my", "i", "me", "please", "help", "fix", "issue",
    "doesn't", "cant", "cannot", "this", "that", "am", "are", "was", "were"
}

def extract_tags(text: str) -> List[str]:
    """Extracts high-value keywords for downstream Vector DB similarity searches."""
    if not text:
        return []
    
    # Remove punctuation and convert to lowercase
    clean_text = re.sub(r'[^\w\s]', '', text.lower())
    words = clean_text.split()
    
    # Filter out stop words and tiny words (like "pc" is fine, but "a" is not)
    # Using a set temporarily removes duplicates, then we convert back to a list
    tags = list(set(word for word in words if word not in STOP_WORDS and len(word) > 1))
    
    return tags