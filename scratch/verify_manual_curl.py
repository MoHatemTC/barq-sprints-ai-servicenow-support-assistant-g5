import hashlib
import hmac
import json
import os
import redis
from fastapi.testclient import TestClient

from App.app import app
from App.resolved_incident_cache import generate_cache_key, get_redis_client

WEBHOOK_SECRET = "my_secret_webhook_key"
os.environ["WEBHOOK_SECRET"] = WEBHOOK_SECRET

client = TestClient(app)

BODY = {
  "sys_id": "e56961280fbf8b148dc3bbc530d1b2ba",
  "number": "INC0010269",
  "short_description": "Laptop drops off home Wi-Fi",
  "description": "Wi-Fi drops every 10-15 minutes",
  "close_code": "Solved Remotely (Permanently)",
  "close_notes": "Forget the network and reconnect; restart the router.",
  "resolved_by": "System Administrator",
  "resolved_at": "2026-10-04 23:50:00",
  "ai_confidence": 0.62,
  "ai_suggested_response": "1. Restart the PC."
}

raw_bytes = json.dumps(BODY).encode("utf-8")
sig = hmac.new(WEBHOOK_SECRET.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()

response = client.post(
    "/api/incident-resolved",
    content=raw_bytes,
    headers={
        "Content-Type": "application/json",
        "X-ServiceNow-Signature": sig
    }
)

print("HTTP Status Code:", response.status_code)
print("Response JSON:", response.json())

key = generate_cache_key(BODY["short_description"], BODY["description"])
r = get_redis_client()
redis_val = r.get(key)
print("Redis Key:", key)
print("Redis Value:", redis_val)
