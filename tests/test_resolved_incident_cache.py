import base64
import hashlib
import hmac
import os
import pytest
from fastapi.testclient import TestClient
import redis

from App.app import app
from App.resolved_incident_cache import (
    generate_cache_key,
    normalize_incident_text,
    get_redis_client,
    ResolvedIncidentCache,
)
from Schemas.Incident_context import IncidentContext
from run_pipeline import process_incident

client = TestClient(app)
WEBHOOK_SECRET = "test_webhook_secret_key_123"


@pytest.fixture(autouse=True)
def setup_env_and_redis(monkeypatch):
    """Fixture to configure WEBHOOK_SECRET and clear Redis keys before each test."""
    monkeypatch.setenv("WEBHOOK_SECRET", WEBHOOK_SECRET)
    
    # Flush test redis database
    try:
        r = get_redis_client()
        r.flushdb()
    except Exception:
        pass
    yield
    try:
        r = get_redis_client()
        r.flushdb()
    except Exception:
        pass


def make_hmac_header(body: bytes, use_b64: bool = False) -> str:
    digest = hmac.new(WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    if use_b64:
        return base64.b64encode(digest).decode("ascii")
    return digest.hex()


def test_1_valid_servicenow_request():
    """Test 1 — Valid ServiceNow request: expect 202 and Redis key written."""
    body_dict = {
        "sys_id": "70c8fc300fb70f148dc3bbc530d1b27c",
        "number": "INC0010291",
        "short_description": "USB or External Storage Device Not Recognized",
        "description": "USB or External Storage Device Not Recognized",
        "close_code": "Solution provided",
        "close_notes": "1. Restart the computer and reconnect USB.",
        "resolved_by": "develop Requester",
        "resolved_at": "2026-10-05 11:12:51",
        "ai_confidence": 0.79,
        "ai_suggested_response": "Suggested resolution..."
    }
    import json
    raw_body = json.dumps(body_dict).encode("utf-8")
    sig = make_hmac_header(raw_body)

    response = client.post(
        "/api/incident-resolved",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-ServiceNow-Signature": sig
        }
    )

    assert response.status_code == 202
    res_json = response.json()
    assert res_json["status"] == "accepted"
    assert res_json["cached"] is True
    assert res_json["sys_id"] == body_dict["sys_id"]

    # Verify Redis contents
    cache_key = generate_cache_key(body_dict["short_description"], body_dict["description"])
    r = get_redis_client()
    val = r.get(cache_key)
    assert val is not None
    data = json.loads(val)
    assert data["close_notes"] == body_dict["close_notes"]
    assert data["source"] == "servicenow"
    assert data["verified"] is True


def test_2_invalid_signature():
    """Test 2 — Invalid signature: expect 401 and nothing written to Redis."""
    body_dict = {
        "sys_id": "70c8fc300fb70f148dc3bbc530d1b27c",
        "number": "INC0010291",
        "short_description": "USB Issue",
        "description": "USB Issue",
        "close_code": "Solution provided",
        "close_notes": "Restart PC",
    }
    import json
    raw_body = json.dumps(body_dict).encode("utf-8")

    response = client.post(
        "/api/incident-resolved",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-ServiceNow-Signature": "invalid_signature_hex"
        }
    )

    assert response.status_code == 401
    cache_key = generate_cache_key("USB Issue", "USB Issue")
    r = get_redis_client()
    assert r.get(cache_key) is None


def test_3_missing_signature():
    """Test 3 — Missing signature header: expect 401."""
    body_dict = {
        "sys_id": "70c8fc300fb70f148dc3bbc530d1b27c",
        "number": "INC0010291",
        "short_description": "USB Issue",
        "close_code": "Solution provided",
        "close_notes": "Restart PC",
    }
    import json
    response = client.post(
        "/api/incident-resolved",
        content=json.dumps(body_dict).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 401


def test_4_invalid_sys_id():
    """Test 4 — Invalid sys_id: expect validation error."""
    body_dict = {
        "sys_id": "123",  # Not 32 hex chars
        "number": "INC0010291",
        "short_description": "USB Issue",
        "close_code": "Solution provided",
        "close_notes": "Restart PC",
    }
    import json
    raw_body = json.dumps(body_dict).encode("utf-8")
    sig = make_hmac_header(raw_body)

    response = client.post(
        "/api/incident-resolved",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-ServiceNow-Signature": sig
        }
    )
    assert response.status_code in (400, 422)


def test_5_empty_close_notes():
    """Test 5 — Empty close_notes: expect validation error and no Redis write."""
    body_dict = {
        "sys_id": "70c8fc300fb70f148dc3bbc530d1b27c",
        "number": "INC0010291",
        "short_description": "USB Issue",
        "close_code": "Solution provided",
        "close_notes": "   ",  # Empty / whitespace only
    }
    import json
    raw_body = json.dumps(body_dict).encode("utf-8")
    sig = make_hmac_header(raw_body)

    response = client.post(
        "/api/incident-resolved",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-ServiceNow-Signature": sig
        }
    )
    assert response.status_code in (400, 422)
    r = get_redis_client()
    assert r.get(generate_cache_key("USB Issue", "")) is None


def test_6_not_solved():
    """Test 6 — Not Solved close_code: expect 202 but no Redis write."""
    body_dict = {
        "sys_id": "70c8fc300fb70f148dc3bbc530d1b27c",
        "number": "INC0010291",
        "short_description": "USB Issue",
        "description": "USB Issue",
        "close_code": "Not Solved (Not Reproducible)",
        "close_notes": "Could not reproduce problem.",
    }
    import json
    raw_body = json.dumps(body_dict).encode("utf-8")
    sig = make_hmac_header(raw_body)

    response = client.post(
        "/api/incident-resolved",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-ServiceNow-Signature": sig
        }
    )

    assert response.status_code == 202
    res_json = response.json()
    assert res_json["status"] == "accepted"
    assert res_json["cached"] is False
    assert res_json["reason"] == "incident_not_solved"

    r = get_redis_client()
    assert r.get(generate_cache_key("USB Issue", "USB Issue")) is None


def test_7_same_incident_text_cache_hit():
    """Test 7 — Same incident text lookup produces Redis HIT."""
    body_dict = {
        "sys_id": "70c8fc300fb70f148dc3bbc530d1b27c",
        "number": "INC0010291",
        "short_description": "Printer Offline Error",
        "description": "Printer is not responding on IP 192.168.1.50",
        "close_code": "Solution provided",
        "close_notes": "Rebooted printer print server.",
    }
    import json
    raw_body = json.dumps(body_dict).encode("utf-8")
    sig = make_hmac_header(raw_body)

    # Store resolution in Redis via POST /api/incident-resolved
    res = client.post(
        "/api/incident-resolved",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-ServiceNow-Signature": sig}
    )
    assert res.status_code == 202

    # Process new incident with exact same text
    ctx = IncidentContext(
        sys_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        original_number="INC0099999",
        short_description="Printer Offline Error",
        description="Printer is not responding on IP 192.168.1.50",
        sanitized_query="Printer Offline Error\nPrinter is not responding on IP 192.168.1.50",
        truncated_description="Printer is not responding on IP 192.168.1.50",
        extracted_tags=["printer"],
        is_safe=True,
    )

    pipeline_res = process_incident(ctx)
    assert pipeline_res["cached"] is True
    assert pipeline_res["source"] == "previously_resolved_incident"
    assert pipeline_res["verified"] is True
    assert pipeline_res["resolution"] == "Rebooted printer print server."


def test_8_whitespace_normalization():
    """Test 8 — Whitespace normalization: variations produce identical key."""
    key1 = generate_cache_key("USB Device Not Recognized", "")
    key2 = generate_cache_key("  USB   Device   Not Recognized  ", "")
    assert key1 == key2

    key3 = generate_cache_key("USB Device", "Line 1 \r\n Line 2   ")
    key4 = generate_cache_key("USB Device", "Line 1\nLine 2")
    assert key3 == key4


def test_9_different_text_cache_miss():
    """Test 9 — Different incident text produces Redis MISS."""
    # Populate cache with Incident A
    body_dict = {
        "sys_id": "70c8fc300fb70f148dc3bbc530d1b27c",
        "number": "INC0010291",
        "short_description": "VPN Disconnecting",
        "description": "VPN drops every 5 mins",
        "close_code": "Solution provided",
        "close_notes": "Update VPN client to v2.4.",
    }
    import json
    raw_body = json.dumps(body_dict).encode("utf-8")
    sig = make_hmac_header(raw_body)
    client.post(
        "/api/incident-resolved",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-ServiceNow-Signature": sig}
    )

    # Process Incident B (completely different text)
    cached_res = ResolvedIncidentCache.get_cached_resolution("Outlook Sync Fail", "Emails stuck in outbox")
    assert cached_res is None


def test_10_re_resolution_upsert():
    """Test 10 — Re-resolution overwrites key with Resolution B."""
    import json
    body_a = {
        "sys_id": "11111111111111111111111111111111",
        "number": "INC0000001",
        "short_description": "Monitor Screen Black",
        "description": "No display signal",
        "close_code": "Solution provided",
        "close_notes": "Resolution A: Replaced DisplayPort cable.",
    }
    raw_a = json.dumps(body_a).encode("utf-8")
    sig_a = make_hmac_header(raw_a)
    client.post("/api/incident-resolved", content=raw_a, headers={"Content-Type": "application/json", "X-ServiceNow-Signature": sig_a})

    body_b = {
        "sys_id": "22222222222222222222222222222222",
        "number": "INC0000002",
        "short_description": "Monitor Screen Black",
        "description": "No display signal",
        "close_code": "Solution provided",
        "close_notes": "Resolution B: Replaced monitor power supply.",
    }
    raw_b = json.dumps(body_b).encode("utf-8")
    sig_b = make_hmac_header(raw_b)
    client.post("/api/incident-resolved", content=raw_b, headers={"Content-Type": "application/json", "X-ServiceNow-Signature": sig_b})

    cached_res = ResolvedIncidentCache.get_cached_resolution("Monitor Screen Black", "No display signal")
    assert cached_res is not None
    assert cached_res["close_notes"] == "Resolution B: Replaced monitor power supply."
    assert cached_res["sys_id"] == "22222222222222222222222222222222"


def test_11_base64_hmac():
    """Test 11 — Base64 HMAC signature verification works."""
    body_dict = {
        "sys_id": "70c8fc300fb70f148dc3bbc530d1b27c",
        "number": "INC0010291",
        "short_description": "Headset Mic Silent",
        "description": "Microphone not picking up audio",
        "close_code": "Solution provided",
        "close_notes": "Unmuted physical switch on cable.",
    }
    import json
    raw_body = json.dumps(body_dict).encode("utf-8")
    b64_sig = make_hmac_header(raw_body, use_b64=True)

    response = client.post(
        "/api/incident-resolved",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-ServiceNow-Signature": b64_sig
        }
    )

    assert response.status_code == 202
    assert response.json()["cached"] is True
