import httpx
import pytest

from src.writeback.servicenow_writeback import (
    ServiceNowWritebackClient,
)


# ============================================================
# SUCCESSFUL WRITE-BACK TESTS
# ============================================================


@pytest.mark.asyncio
async def test_suggest_sends_correct_payload(monkeypatch):
    captured = {}

    async def mock_patch(self, url, **kwargs):
        captured["method"] = "PATCH"
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        captured["auth"] = kwargs.get("auth")

        return httpx.Response(
            status_code=200,
            json={"result": {"sys_id": "abc123"}},
            request=httpx.Request("PATCH", url),
        )

    monkeypatch.setattr(
        httpx.AsyncClient,
        "patch",
        mock_patch,
    )

    client = ServiceNowWritebackClient(
        instance_url="https://example.service-now.com",
        username="test_user",
        password="test_password",
    )

    result = await client.suggest(
        sys_id="abc123",
        ai_suggested_response="Please restart the service.",
        ai_confidence=0.92,
    )

    assert result["ok"] is True

    assert captured["method"] == "PATCH"

    assert captured["url"] == (
        "https://example.service-now.com"
        "/api/now/table/incident/abc123"
    )

    assert captured["json"] == {
        "x_2216229_sprint_1_ai_status": "suggested",
        "x_2216229_sprint_1_ai_suggested_response": "Please restart the service.",
        "x_2216229_sprint_1_ai_confidence": 0.92,
        "x_2216229_sprint_1_human_review_required": True,
        "x_2216229_sprint_1_ai_processed": True,
    }

    assert captured["auth"] == (
        "test_user",
        "test_password",
    )


@pytest.mark.asyncio
async def test_add_work_note_uses_internal_work_notes_only(
    monkeypatch,
):
    captured = {}

    async def mock_patch(self, url, **kwargs):
        captured["json"] = kwargs.get("json")

        return httpx.Response(
            status_code=200,
            json={"result": {"sys_id": "abc123"}},
            request=httpx.Request("PATCH", url),
        )

    monkeypatch.setattr(
        httpx.AsyncClient,
        "patch",
        mock_patch,
    )

    client = ServiceNowWritebackClient(
        instance_url="https://example.service-now.com",
        username="test_user",
        password="test_password",
    )

    result = await client.add_work_note(
        sys_id="abc123",
        note="AI escalated this incident for human review.",
    )

    assert result["ok"] is True

    assert captured["json"] == {
        "work_notes": (
            "AI escalated this incident for human review."
        ),
    }

    assert "comments" not in captured["json"]


@pytest.mark.asyncio
async def test_escalate_sends_correct_payload(monkeypatch):
    captured = {}

    async def mock_patch(self, url, **kwargs):
        captured["method"] = "PATCH"
        captured["url"] = url
        captured["json"] = kwargs.get("json")

        return httpx.Response(
            status_code=200,
            json={"result": {"sys_id": "abc123"}},
            request=httpx.Request("PATCH", url),
        )

    monkeypatch.setattr(
        httpx.AsyncClient,
        "patch",
        mock_patch,
    )

    client = ServiceNowWritebackClient(
        instance_url="https://example.service-now.com",
        username="test_user",
        password="test_password",
    )

    result = await client.escalate(
        sys_id="abc123",
        reason=(
            "AI confidence is too low "
            "for an automatic response."
        ),
    )

    assert result["ok"] is True

    assert captured["method"] == "PATCH"

    assert captured["url"] == (
        "https://example.service-now.com"
        "/api/now/table/incident/abc123"
    )

    assert captured["json"] == {
        "x_2216229_sprint_1_ai_status": "escalated",
        "x_2216229_sprint_1_ai_suggested_response": "",
        "x_2216229_sprint_1_human_review_required": False,
        "work_notes": (
            "AI escalation reason: "
            "AI confidence is too low "
            "for an automatic response."
        ),
    }

    assert "comments" not in captured["json"]


# ============================================================
# SECURITY / ALLOW-LIST TESTS
# ============================================================


@pytest.mark.asyncio
async def test_allow_list_rejects_unauthorized_fields(
    monkeypatch,
):
    http_called = False

    async def mock_patch(self, url, **kwargs):
        nonlocal http_called
        http_called = True

        return httpx.Response(
            status_code=200,
            json={"result": {"sys_id": "abc123"}},
            request=httpx.Request("PATCH", url),
        )

    monkeypatch.setattr(
        httpx.AsyncClient,
        "patch",
        mock_patch,
    )

    client = ServiceNowWritebackClient(
        instance_url="https://example.service-now.com",
        username="test_user",
        password="test_password",
    )

    result = await client._patch(
        sys_id="abc123",
        payload={
            "state": "6",
        },
    )

    assert result["ok"] is False

    assert (
        "Unauthorized ServiceNow fields"
        in result["error"]
    )

    assert "state" in result["error"]

    assert http_called is False


@pytest.mark.parametrize(
    "unauthorized_field",
    [
        "state",
        "assigned_to",
        "assignment_group",
        "close_code",
        "close_notes",
    ],
)
@pytest.mark.asyncio
async def test_allow_list_rejects_sensitive_fields(
    unauthorized_field,
):
    client = ServiceNowWritebackClient(
        instance_url="https://example.service-now.com",
        username="test_user",
        password="test_password",
    )

    result = await client._patch(
        sys_id="abc123",
        payload={
            unauthorized_field: "malicious-value",
        },
    )

    assert result["ok"] is False

    assert (
        "Unauthorized ServiceNow fields"
        in result["error"]
    )

    assert unauthorized_field in result["error"]


# ============================================================
# CONFIDENCE VALIDATION TESTS
# ============================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_confidence",
    [
        -0.1,
        1.1,
        2.0,
        -1.0,
    ],
)
async def test_suggest_rejects_invalid_confidence(
    invalid_confidence,
):
    client = ServiceNowWritebackClient(
        instance_url="https://example.service-now.com",
        username="test_user",
        password="test_password",
    )

    result = await client.suggest(
        sys_id="abc123",
        ai_suggested_response=(
            "Please restart the service."
        ),
        ai_confidence=invalid_confidence,
    )

    assert result["ok"] is False

    assert (
        "ai_confidence must be between 0.0 and 1.0"
        in result["error"]
    )


@pytest.mark.asyncio
async def test_suggest_rejects_boolean_confidence():
    client = ServiceNowWritebackClient(
        instance_url="https://example.service-now.com",
        username="test_user",
        password="test_password",
    )

    result = await client.suggest(
        sys_id="abc123",
        ai_suggested_response=(
            "Please restart the service."
        ),
        ai_confidence=True,
    )

    assert result["ok"] is False

    assert (
        "ai_confidence must be a number"
        in result["error"]
    )


# ============================================================
# HTTP FAILURE TESTS
# ============================================================


@pytest.mark.asyncio
async def test_non_transient_http_error_does_not_retry(
    monkeypatch,
):
    call_count = 0

    async def mock_patch(self, url, **kwargs):
        nonlocal call_count
        call_count += 1

        return httpx.Response(
            status_code=400,
            json={
                "error": "Bad Request",
            },
            request=httpx.Request("PATCH", url),
        )

    monkeypatch.setattr(
        httpx.AsyncClient,
        "patch",
        mock_patch,
    )

    client = ServiceNowWritebackClient(
        instance_url="https://example.service-now.com",
        username="test_user",
        password="test_password",
        max_retries=3,
    )

    result = await client.suggest(
        sys_id="abc123",
        ai_suggested_response=(
            "Please restart the service."
        ),
        ai_confidence=0.92,
    )

    assert result["ok"] is False

    assert "400" in result["error"]

    # 400 is not transient.
    # Therefore, there must be no retry.
    assert call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code",
    [
        429,
        503,
    ],
)
async def test_transient_http_error_retries_then_succeeds(
    monkeypatch,
    status_code,
):
    call_count = 0
    sleep_delays = []

    async def mock_patch(self, url, **kwargs):
        nonlocal call_count
        call_count += 1

        if call_count < 3:
            return httpx.Response(
                status_code=status_code,
                json={
                    "error": "Temporary failure",
                },
                request=httpx.Request(
                    "PATCH",
                    url,
                ),
            )

        return httpx.Response(
            status_code=200,
            json={
                "result": {
                    "sys_id": "abc123",
                },
            },
            request=httpx.Request(
                "PATCH",
                url,
            ),
        )

    async def fake_sleep(delay):
        sleep_delays.append(delay)

    monkeypatch.setattr(
        httpx.AsyncClient,
        "patch",
        mock_patch,
    )

    monkeypatch.setattr(
        "src.writeback.servicenow_writeback.asyncio.sleep",
        fake_sleep,
    )

    client = ServiceNowWritebackClient(
        instance_url="https://example.service-now.com",
        username="test_user",
        password="test_password",
        max_retries=3,
    )

    result = await client.suggest(
        sys_id="abc123",
        ai_suggested_response=(
            "Please restart the service."
        ),
        ai_confidence=0.92,
    )

    assert result["ok"] is True

    # First attempt + two retries.
    assert call_count == 3

    # Retry delays are:
    # attempt 0 -> 1 second
    # attempt 1 -> 2 seconds
    assert sleep_delays == [1, 2]


@pytest.mark.asyncio
async def test_transient_http_error_stops_after_max_retries(
    monkeypatch,
):
    call_count = 0
    sleep_delays = []

    async def mock_patch(self, url, **kwargs):
        nonlocal call_count
        call_count += 1

        return httpx.Response(
            status_code=503,
            json={
                "error": "Service Unavailable",
            },
            request=httpx.Request(
                "PATCH",
                url,
            ),
        )

    async def fake_sleep(delay):
        sleep_delays.append(delay)

    monkeypatch.setattr(
        httpx.AsyncClient,
        "patch",
        mock_patch,
    )

    monkeypatch.setattr(
        "src.writeback.servicenow_writeback.asyncio.sleep",
        fake_sleep,
    )

    client = ServiceNowWritebackClient(
        instance_url="https://example.service-now.com",
        username="test_user",
        password="test_password",
        max_retries=2,
    )

    result = await client.suggest(
        sys_id="abc123",
        ai_suggested_response=(
            "Please restart the service."
        ),
        ai_confidence=0.92,
    )

    assert result["ok"] is False

    assert "503" in result["error"]

    assert "3 attempts" in result["error"]

    # max_retries=2 means:
    # initial request + 2 retries = 3 attempts
    assert call_count == 3

    assert sleep_delays == [1, 2]


@pytest.mark.asyncio
async def test_timeout_retries_until_exhausted(
    monkeypatch,
):
    call_count = 0
    sleep_delays = []

    async def mock_patch(self, url, **kwargs):
        nonlocal call_count
        call_count += 1

        raise httpx.ReadTimeout(
            "request timed out",
            request=httpx.Request(
                "PATCH",
                url,
            ),
        )

    async def fake_sleep(delay):
        sleep_delays.append(delay)

    monkeypatch.setattr(
        httpx.AsyncClient,
        "patch",
        mock_patch,
    )

    monkeypatch.setattr(
        "src.writeback.servicenow_writeback.asyncio.sleep",
        fake_sleep,
    )

    client = ServiceNowWritebackClient(
        instance_url="https://example.service-now.com",
        username="test_user",
        password="test_password",
        max_retries=2,
    )

    result = await client.suggest(
        sys_id="abc123",
        ai_suggested_response=(
            "Please restart the service."
        ),
        ai_confidence=0.92,
    )

    assert result["ok"] is False

    assert (
        "ServiceNow request failed"
        in result["error"]
    )

    # Initial request + 2 retries.
    assert call_count == 3

    assert sleep_delays == [1, 2]


# ============================================================
# INPUT VALIDATION TESTS
# ============================================================


@pytest.mark.asyncio
async def test_add_work_note_rejects_empty_note():
    client = ServiceNowWritebackClient(
        instance_url="https://example.service-now.com",
        username="test_user",
        password="test_password",
    )

    result = await client.add_work_note(
        sys_id="abc123",
        note="   ",
    )

    assert result["ok"] is False

    assert "note must be a non-empty string" in result["error"]


@pytest.mark.asyncio
async def test_suggest_rejects_empty_response():
    client = ServiceNowWritebackClient(
        instance_url="https://example.service-now.com",
        username="test_user",
        password="test_password",
    )

    result = await client.suggest(
        sys_id="abc123",
        ai_suggested_response="   ",
        ai_confidence=0.9,
    )

    assert result["ok"] is False

    assert (
        "ai_suggested_response must be a non-empty string"
        in result["error"]
    )


@pytest.mark.asyncio
async def test_escalate_rejects_empty_reason():
    client = ServiceNowWritebackClient(
        instance_url="https://example.service-now.com",
        username="test_user",
        password="test_password",
    )

    result = await client.escalate(
        sys_id="abc123",
        reason="   ",
    )

    assert result["ok"] is False

    assert (
        "reason must be a non-empty string"
        in result["error"]
    )