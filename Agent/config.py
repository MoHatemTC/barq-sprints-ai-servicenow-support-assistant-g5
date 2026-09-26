"""Central configuration parameters for the Agent Tool Layer (Sprint 3.3).

All parameters governing tool execution, thresholds, truncation, and
validation are centralized here as single sources of truth.
"""

import os
from typing import Tuple
from dotenv import load_dotenv

load_dotenv()

# Qdrant & Retrieval Parameters
TOP_K: int = int(os.getenv("TOP_K", "5"))
SCORE_THRESHOLD: float = float(os.getenv("SCORE_THRESHOLD", "0.70"))
ALLOWED_WORKFLOW_STATES: Tuple[str, ...] = tuple(
    s.strip().lower()
    for s in os.getenv("ALLOWED_WORKFLOW_STATES", "published").split(",")
    if s.strip()
)

# Embedding & Collection defaults
DEFAULT_EMBEDDING_MODEL_NAME: str = "BAAI/bge-base-en-v1.5"
EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME") or DEFAULT_EMBEDDING_MODEL_NAME
EMBEDDING_VECTOR_SIZE: int = int(os.getenv("EMBEDDING_VECTOR_SIZE", "768"))
QDRANT_COLLECTION_PREFIX: str = os.getenv("QDRANT_COLLECTION_PREFIX", "kb")

# Tool-Specific Validation Constraints
MAX_NOTE_LENGTH: int = int(os.getenv("MAX_NOTE_LENGTH", "4000"))
MIN_REASON_LENGTH: int = int(os.getenv("MIN_REASON_LENGTH", "5"))

# Security Constraints: Strictly forbidden actions on read-only / advisory agent
FORBIDDEN_TOOL_WORDS: Tuple[str, ...] = (
    "update",
    "write",
    "delete",
    "close",
    "resolve",
    "assign",
    "reassign",
    "create",
    "patch",
)
