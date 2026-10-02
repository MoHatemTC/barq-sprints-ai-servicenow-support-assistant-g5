"""tests/test_query_normalizer.py

Offline unit tests for the 3-Tier Defense-in-Depth system.
Tests entropy math, Arabic/English credential masking, and post-flight validation.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from utils.sanitizer import mask_pii, calculate_shannon_entropy
from Services.query_normalizer import NormalizedIncident, normalize_incident


# --- Tier 1 Tests (Regex + Entropy) ---

def test_tier1_masks_arabic_credentials():
    arabic_text = "الباسورد بتاعي هو Admin@2024 ومش عارف ادخل على السيستم"
    masked = mask_pii(arabic_text)
    assert "Admin@2024" not in masked
    assert "[REDACTED_CREDENTIAL]" in masked


def test_tier1_masks_english_and_ip():
    text = "password: SuperSecret123 connecting to server 192.168.1.100"
    masked = mask_pii(text)
    assert "SuperSecret123" not in masked
    assert "192.168.1.100" not in masked
    assert "[REDACTED_CREDENTIAL]" in masked
    assert "[REDACTED_IP]" in masked


def test_tier1_entropy_catches_unlabeled_password():
    # 'Winter2024!' has no 'password:' label, but high entropy
    entropy = calculate_shannon_entropy("Winter2024!")
    assert entropy > 3.0

    raw = "I tried typing Winter2024! into the portal but it failed"
    masked = mask_pii(raw)
    assert "Winter2024!" not in masked
    assert "[REDACTED_CREDENTIAL]" in masked


# --- Tier 2 & Tier 3 Tests (Normalizer & Post-Flight) ---

@pytest.fixture
def mock_llm(monkeypatch):
    mock = MagicMock()
    structured = MagicMock()
    mock.with_structured_output.return_value = structured
    monkeypatch.setattr("Services.query_normalizer.get_llm", lambda: mock)
    return structured


def test_tier2_normalizer_extracts_clean_english_query(mock_llm):
    mock_llm.invoke.return_value = NormalizedIncident(
        affected_system="Cisco AnyConnect",
        core_technical_symptom="VPN connection authentication failure",
        detected_error_codes=["AUTH-403"],
        urgency_sentiment="frustrated",
        optimized_search_query="Cisco AnyConnect VPN connection authentication failure AUTH-403",
    )

    ticket = "I am so mad! Cisco VPN broke right before my meeting! Auth failed 403!"
    result = normalize_incident(ticket)

    assert result.affected_system == "Cisco AnyConnect"
    assert "mad" not in result.optimized_search_query
    assert "meeting" not in result.optimized_search_query
    assert result.optimized_search_query == "Cisco AnyConnect VPN connection authentication failure AUTH-403"


def test_tier3_post_flight_clamps_length(mock_llm):
    mock_llm.invoke.return_value = NormalizedIncident(
        core_technical_symptom="issue",
        optimized_search_query="A" * 300,  # Maliciously long query
    )
    result = normalize_incident("some text")
    assert len(result.optimized_search_query) <= 120


def test_normalizer_graceful_fallback_on_llm_failure(monkeypatch):
    def crash():
        raise RuntimeError("LiteLLM 503 Service Unavailable")

    monkeypatch.setattr("Services.query_normalizer.get_llm", crash)

    raw_input = "wifi keeps dropping on laptop"
    result = normalize_incident(raw_input)

    assert isinstance(result, NormalizedIncident)
    assert "wifi" in result.optimized_search_query.lower()