import hashlib
import json
import logging
import os
import re
from typing import Any, Dict, Optional
import redis

logger = logging.getLogger("servicenow_webhook.resolved_cache")


def normalize_incident_text(text: Optional[str]) -> str:
    """
    Deterministic and minimal normalization for exact-match caching.
    1. Convert None to empty string.
    2. Normalize line endings (\r\n -> \n, \r -> \n).
    3. Strip leading/trailing whitespace.
    4. Collapse repeated horizontal spaces and tabs into a single space per line.
    """
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [re.sub(r"[ \t]+", " ", line.strip()) for line in text.split("\n")]
    return "\n".join(lines)


def generate_cache_key(short_description: Optional[str], description: Optional[str]) -> str:
    """
    Generates SHA-256 exact-match cache key from normalized short_description + description.
    Key format: resolved_incident:<hash>
    """
    norm_short = normalize_incident_text(short_description)
    norm_desc = normalize_incident_text(description)
    cache_input = f"{norm_short}\n{norm_desc}"
    cache_hash = hashlib.sha256(cache_input.encode("utf-8")).hexdigest()
    return f"resolved_incident:{cache_hash}"


def get_redis_client() -> redis.Redis:
    """
    Returns a Redis client using REDIS_URL or REDIS_HOST/REDIS_PORT environment variables.
    """
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        return redis.Redis.from_url(redis_url, decode_responses=True)

    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", "6379"))
    return redis.Redis(host=host, port=port, decode_responses=True)


class ResolvedIncidentCache:
    """
    Exact-match Redis cache for human-verified resolved ServiceNow incidents.
    """

    @staticmethod
    def get_cached_resolution(short_description: Optional[str], description: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Lookup previously verified resolution in Redis by exact match.
        Returns deserialized JSON dict if HIT, None if MISS or error.
        """
        key = generate_cache_key(short_description, description)
        try:
            client = get_redis_client()
            val = client.get(key)
            if val:
                logger.info("Cache HIT for key %s", key)
                return json.loads(val)
            logger.info("Cache MISS for key %s", key)
            return None
        except Exception as exc:
            logger.warning("Redis connection or lookup failed: %s", exc)
            return None

    @staticmethod
    def set_cached_resolution(key: str, data: Dict[str, Any]) -> bool:
        """
        Store/upsert verified ServiceNow resolution in Redis using SET.
        Raises exception if Redis is unavailable.
        """
        client = get_redis_client()
        val = json.dumps(data)
        client.set(key, val)
        logger.info("Stored resolved incident in Redis for key %s", key)
        return True
