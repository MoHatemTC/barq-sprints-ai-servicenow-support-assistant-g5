import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest

# Ensure workspace root is on sys.path so 'Services' imports correctly anywhere
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from Services.query_normalizer import NormalizedIncident, normalize_incident


@pytest.fixture
def mock_normalizer_llm(monkeypatch):
    """Mocks LiteLLM structured output for deterministic unit testing."""
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    monkeypatch.setattr("Services.query_normalizer.get_llm", lambda: mock_llm)
    return mock_structured


def test_normalizer_strips_emotion_and_urgency(mock_normalizer_llm):
    """Verify that emotional venting and urgency markers are stripped from the search query."""
    mock_normalizer_llm.invoke.return_value = NormalizedIncident(
        affected_system="Cisco AnyConnect",
        core_technical_symptom="VPN connection authentication failure",
        detected_error_codes=["AUTH-403"],
        urgency_sentiment="frustrated",
        optimized_search_query="Cisco AnyConnect VPN connection authentication failure AUTH-403",
    )

    noisy_ticket = (
        "I AM LIVID!! Cisco VPN completely broke 5 minutes before my executive presentation! "
        "Fix this immediately, it says AUTH-403! My boss is going to fire me!"
    )
    result = normalize_incident(noisy_ticket)

    assert result.affected_system == "Cisco AnyConnect"
    assert "LIVID" not in result.optimized_search_query
    assert "presentation" not in result.optimized_search_query
    assert "boss" not in result.optimized_search_query
    assert "AUTH-403" in result.optimized_search_query
    assert result.optimized_search_query == "Cisco AnyConnect VPN connection authentication failure AUTH-403"


def test_normalizer_translates_colloquial_slang(mock_normalizer_llm):
    """Verify that colloquial slang is translated into enterprise IT terms."""
    mock_normalizer_llm.invoke.return_value = NormalizedIncident(
        affected_system="Cisco AnyConnect VPN",
        core_technical_symptom="remote access connection timeout",
        detected_error_codes=[],
        urgency_sentiment="neutral",
        optimized_search_query="Cisco AnyConnect VPN remote access connection timeout",
    )

    colloquial_ticket = "The blue padlock icon program won't let me work from my hotel room."
    result = normalize_incident(colloquial_ticket)

    assert "blue padlock" not in result.optimized_search_query
    assert "Cisco AnyConnect" in result.optimized_search_query
    assert result.core_technical_symptom == "remote access connection timeout"


def test_normalizer_handles_empty_input():
    """Verify that empty inputs do not crash or throw exceptions."""
    res_empty = normalize_incident("   ")
    assert res_empty.core_technical_symptom == "unspecified issue"
    assert len(res_empty.optimized_search_query) > 0


def test_normalizer_graceful_fallback_on_llm_failure(monkeypatch):
    """Verify that if the LLM provider is down (503 / timeout), it falls back safely to raw text."""
    def crash():
        raise RuntimeError("LiteLLM 503 Service Unavailable")

    monkeypatch.setattr("Services.query_normalizer.get_llm", crash)

    raw_input = "wifi keeps disconnecting randomly on windows 11 laptop"
    result = normalize_incident(raw_input)

    assert isinstance(result, NormalizedIncident)
    assert "wifi" in result.optimized_search_query.lower()
    assert result.core_technical_symptom != ""


def test_normalizer_clamps_query_length(mock_normalizer_llm):
    """Verify that the search query is strictly clamped to prevent prompt smuggling."""
    mock_normalizer_llm.invoke.return_value = NormalizedIncident(
        core_technical_symptom="long issue",
        optimized_search_query="A" * 300,  # Maliciously long query
    )

    result = normalize_incident("some issue")
    assert len(result.optimized_search_query) <= 120
