import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.writeback.servicenow_writeback import ServiceNowWritebackClient


BASE_URL = "https://dev394438.service-now.com"
USERNAME = "integration_user"
PASSWORD = "integration_password"
SYS_ID = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def client() -> ServiceNowWritebackClient:
    return ServiceNowWritebackClient(
        instance_url=BASE_URL,
        username=USERNAME,
        password=PASSWORD,
        timeout=10,
        max_retries=3,
    )


def make_response(status_code: int) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        request=httpx.Request(
            "PATCH",
            f"{BASE_URL}/api/now/table/incident/{SYS_ID}",
        ),
    )


# ---------------------------------------------------------------------------
# Constructor / configuration
# ---------------------------------------------------------------------------

def test_client_initializes_with_explicit_configuration():
    client = ServiceNowWritebackClient(
        instance_url=BASE_URL,
        username=USERNAME,
        password=PASSWORD,
        timeout=5,
        max_retries=2,
    )

    assert client.instance_url == BASE_URL
    assert client.username == USERNAME
    assert client.password == PASSWORD
    assert client.timeout == 5
    assert client.max_retries == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "instance_url": "",
            "username": USERNAME,
            "password": PASSWORD,
        },
        {
            "instance_url": BASE_URL,
            "username": "",
            "password": PASSWORD,
        },
        {
            "instance_url": BASE_URL,
            "username": USERNAME,
            "password": "",
        },
    ],
)
def test_constructor_rejects_missing_configuration(kwargs):
    with pytest.raises(ValueError):
        ServiceNowWritebackClient(**kwargs)


def test_constructor_rejects_negative_max_retries():
    with pytest.raises(ValueError, match="max_retries must be >= 0"):
        ServiceNowWritebackClient(
            instance_url=BASE_URL,
            username=USERNAME,
            password=PASSWORD,
            max_retries=-1,
        )


def test_constructor_rejects_non_positive_timeout():
    with pytest.raises(ValueError, match="timeout must be > 0"):
        ServiceNowWritebackClient(
            instance_url=BASE_URL,
            username=USERNAME,
            password=PASSWORD,
            timeout=0,
        )


# ---------------------------------------------------------------------------
# Helper validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "sys_id",
    ["", " ", None, 123, False],
)
@pytest.mark.asyncio
async def test_suggest_rejects_invalid_sys_id(client, sys_id):
    result = await client.suggest(
        sys_id=sys_id,
        ai_suggested_response="Suggested response",
        ai_confidence=0.8,
    )

    assert result["ok"] is False
    assert "sys_id must be a non-empty string" in result["error"]


@pytest.mark.parametrize(
    "response",
    ["", " ", None, 123, False],
)
@pytest.mark.asyncio
async def test_suggest_rejects_invalid_response_parameter(client, response):
    result = await client.suggest(
        sys_id=SYS_ID,
        ai_suggested_response=response,
        ai_confidence=0.8,
    )

    assert result["ok"] is False
    assert "ai_suggested_response must be a non-empty string" in result["error"]


@pytest.mark.parametrize(
    "confidence",
    [None, "0.8", object()],
)
@pytest.mark.asyncio
async def test_suggest_rejects_non_numeric_confidence(client, confidence):
    result = await client.suggest(
        sys_id=SYS_ID,
        ai_suggested_response="Suggested response",
        ai_confidence=confidence,
    )

    assert result["ok"] is False
    assert "ai_confidence must be a number" in result["error"]


@pytest.mark.parametrize(
    "confidence",
    [-0.01, 1.01, -1, 2],
)
@pytest.mark.asyncio
async def test_suggest_rejects_out_of_range_confidence(client, confidence):
    result = await client.suggest(
        sys_id=SYS_ID,
        ai_suggested_response="Suggested response",
        ai_confidence=confidence,
    )

    assert result["ok"] is False
    assert "ai_confidence must be between 0.0 and 1.0" in result["error"]


@pytest.mark.parametrize(
    "confidence",
    [0.0, 0.5, 1.0],
)
@pytest.mark.asyncio
async def test_suggest_accepts_valid_confidence(client, confidence):
    with patch.object(
        client,
        "_patch",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ) as mock_patch:
        result = await client.suggest(
            sys_id=SYS_ID,
            ai_suggested_response="Suggested response",
            ai_confidence=confidence,
        )

    assert result == {"ok": True}
    mock_patch.assert_awaited_once()

    _, payload = mock_patch.await_args.args
    assert payload["x_2216229_sprint_1_ai_confidence"] == float(confidence)


@pytest.mark.asyncio
async def test_suggest_rejects_boolean_confidence(client):
    result = await client.suggest(
        sys_id=SYS_ID,
        ai_suggested_response="Suggested response",
        ai_confidence=True,
    )

    assert result["ok"] is False
    assert "ai_confidence must be a number" in result["error"]


@pytest.mark.parametrize(
    "reason",
    ["", " ", None, 123, False],
)
@pytest.mark.asyncio
async def test_escalate_rejects_invalid_reason(client, reason):
    result = await client.escalate(
        sys_id=SYS_ID,
        reason=reason,
    )

    assert result["ok"] is False
    assert "reason must be a non-empty string" in result["error"]


@pytest.mark.parametrize(
    "note",
    ["", " ", None, 123, False],
)
@pytest.mark.asyncio
async def test_work_note_rejects_invalid_note(client, note):
    result = await client.add_work_note(
        sys_id=SYS_ID,
        note=note,
    )

    assert result["ok"] is False
    assert "note must be a non-empty string" in result["error"]


# ---------------------------------------------------------------------------
# Successful write-back operations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_suggest_sends_correct_payload(client):
    with patch.object(
        client,
        "_patch",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ) as mock_patch:
        result = await client.suggest(
            sys_id=SYS_ID,
            ai_suggested_response="  Suggested resolution  ",
            ai_confidence=0.87,
        )

    assert result == {"ok": True}

    mock_patch.assert_awaited_once_with(
        SYS_ID,
        {
            "x_2216229_sprint_1_ai_status": "suggested",
            "x_2216229_sprint_1_ai_suggested_response": "Suggested resolution",
            "x_2216229_sprint_1_ai_confidence": 0.87,
            "x_2216229_sprint_1_human_review_required": True,
            "x_2216229_sprint_1_ai_processed": True,
        },
    )


@pytest.mark.asyncio
async def test_escalate_sends_correct_payload(client):
    with patch.object(
        client,
        "_patch",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ) as mock_patch:
        result = await client.escalate(
            sys_id=SYS_ID,
            reason="  Confidence below threshold  ",
        )

    assert result == {"ok": True}

    mock_patch.assert_awaited_once_with(
        SYS_ID,
        {
            "x_2216229_sprint_1_ai_status": "escalated",
            "x_2216229_sprint_1_ai_suggested_response": "",
            "x_2216229_sprint_1_human_review_required": False,
            "work_notes": "AI escalation reason: Confidence below threshold",
        },
    )


@pytest.mark.asyncio
async def test_add_work_note_writes_only_work_notes(client):
    with patch.object(
        client,
        "_patch",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ) as mock_patch:
        result = await client.add_work_note(
            sys_id=SYS_ID,
            note="  Internal review note  ",
        )

    assert result == {"ok": True}

    mock_patch.assert_awaited_once_with(
        SYS_ID,
        {
            "work_notes": "Internal review note",
        },
    )


# ---------------------------------------------------------------------------
# Allow-list enforcement
# ---------------------------------------------------------------------------

def test_allowed_fields_contains_only_expected_writeback_fields():
    assert ServiceNowWritebackClient.ALLOWED_FIELDS == {
        "x_2216229_sprint_1_ai_status",
        "x_2216229_sprint_1_ai_confidence",
        "x_2216229_sprint_1_ai_suggested_response",
        "x_2216229_sprint_1_human_review_required",
        "x_2216229_sprint_1_ai_processed",
        "work_notes",
    }


@pytest.mark.parametrize(
    "unauthorized_field",
    [
        "comments",
        "state",
        "assigned_to",
        "assignment_group",
        "close_code",
        "close_notes",
        "short_description",
        "description",
        "priority",
    ],
)
def test_validate_payload_rejects_unauthorized_fields(unauthorized_field):
    payload = {
        unauthorized_field: "unauthorized value",
    }

    with pytest.raises(
        ValueError,
        match="Unauthorized ServiceNow fields",
    ):
        ServiceNowWritebackClient._validate_payload(payload)


def test_validate_payload_accepts_all_allowed_fields():
    payload = {
        "x_2216229_sprint_1_ai_status": "suggested",
        "x_2216229_sprint_1_ai_confidence": 0.8,
        "x_2216229_sprint_1_ai_suggested_response": "Response",
        "x_2216229_sprint_1_human_review_required": True,
        "x_2216229_sprint_1_ai_processed": True,
        "work_notes": "Internal note",
    }

    ServiceNowWritebackClient._validate_payload(payload)


@pytest.mark.asyncio
async def test_patch_enforces_allow_list_before_http_request(client):
    unauthorized_payload = {
        "comments": "This must never be sent directly",
    }

    with patch(
        "src.writeback.servicenow_writeback.httpx.AsyncClient"
    ) as mock_client:
        result = await client._patch(
            SYS_ID,
            unauthorized_payload,
        )

    assert result["ok"] is False
    assert "Unauthorized ServiceNow fields" in result["error"]
    mock_client.assert_not_called()


@pytest.mark.asyncio
async def test_patch_rejects_invalid_sys_id_before_http_request(client):
    with patch(
        "src.writeback.servicenow_writeback.httpx.AsyncClient"
    ) as mock_client:
        result = await client._patch(
            "",
            {
                "work_notes": "Internal note",
            },
        )

    assert result["ok"] is False
    assert "sys_id must be a non-empty string" in result["error"]
    mock_client.assert_not_called()


# ---------------------------------------------------------------------------
# HTTP PATCH behavior
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_returns_success_for_2xx_response(client):
    response = make_response(200)

    mock_http_client = AsyncMock()
    mock_http_client.patch.return_value = response

    with patch(
        "src.writeback.servicenow_writeback.httpx.AsyncClient"
    ) as mock_client_class:
        mock_client_class.return_value.__aenter__.return_value = mock_http_client
        mock_client_class.return_value.__aexit__.return_value = None

        result = await client._patch(
            SYS_ID,
            {
                "work_notes": "Internal note",
            },
        )

    assert result == {"ok": True}
    mock_http_client.patch.assert_awaited_once()


@pytest.mark.asyncio
async def test_patch_returns_failure_for_non_transient_http_error(client):
    response = make_response(400)

    mock_http_client = AsyncMock()
    mock_http_client.patch.return_value = response

    with patch(
        "src.writeback.servicenow_writeback.httpx.AsyncClient"
    ) as mock_client_class:
        mock_client_class.return_value.__aenter__.return_value = mock_http_client
        mock_client_class.return_value.__aexit__.return_value = None

        result = await client._patch(
            SYS_ID,
            {
                "work_notes": "Internal note",
            },
        )

    assert result == {
        "ok": False,
        "error": "ServiceNow HTTP error 400.",
    }

    mock_http_client.patch.assert_awaited_once()


@pytest.mark.asyncio
async def test_patch_retries_transient_http_error_then_succeeds(client):
    first_response = make_response(503)
    second_response = make_response(200)

    mock_http_client = AsyncMock()
    mock_http_client.patch.side_effect = [
        first_response,
        second_response,
    ]

    with patch(
        "src.writeback.servicenow_writeback.httpx.AsyncClient"
    ) as mock_client_class:
        mock_client_class.return_value.__aenter__.return_value = mock_http_client
        mock_client_class.return_value.__aexit__.return_value = None

        with patch(
            "src.writeback.servicenow_writeback.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            result = await client._patch(
                SYS_ID,
                {
                    "work_notes": "Internal note",
                },
            )

    assert result == {"ok": True}
    assert mock_http_client.patch.await_count == 2
    mock_sleep.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_patch_retries_until_max_retries_then_fails(client):
    response = make_response(503)

    mock_http_client = AsyncMock()
    mock_http_client.patch.return_value = response

    with patch(
        "src.writeback.servicenow_writeback.httpx.AsyncClient"
    ) as mock_client_class:
        mock_client_class.return_value.__aenter__.return_value = mock_http_client
        mock_client_class.return_value.__aexit__.return_value = None

        with patch(
            "src.writeback.servicenow_writeback.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            result = await client._patch(
                SYS_ID,
                {
                    "work_notes": "Internal note",
                },
            )

    assert result["ok"] is False
    assert "503" in result["error"]
    assert "4 attempts" in result["error"]
    assert mock_http_client.patch.await_count == 4
    assert mock_sleep.await_count == 3

    mock_sleep.assert_any_await(1)
    mock_sleep.assert_any_await(2)
    mock_sleep.assert_any_await(4)


@pytest.mark.asyncio
async def test_patch_retries_network_error_then_succeeds(client):
    mock_http_client = AsyncMock()

    mock_http_client.patch.side_effect = [
        httpx.NetworkError("temporary network failure"),
        make_response(200),
    ]

    with patch(
        "src.writeback.servicenow_writeback.httpx.AsyncClient"
    ) as mock_client_class:
        mock_client_class.return_value.__aenter__.return_value = mock_http_client
        mock_client_class.return_value.__aexit__.return_value = None

        with patch(
            "src.writeback.servicenow_writeback.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            result = await client._patch(
                SYS_ID,
                {
                    "work_notes": "Internal note",
                },
            )

    assert result == {"ok": True}
    assert mock_http_client.patch.await_count == 2
    mock_sleep.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_patch_returns_failure_after_network_retries_exhausted(client):
    mock_http_client = AsyncMock()

    mock_http_client.patch.side_effect = httpx.NetworkError(
        "network unavailable"
    )

    with patch(
        "src.writeback.servicenow_writeback.httpx.AsyncClient"
    ) as mock_client_class:
        mock_client_class.return_value.__aenter__.return_value = mock_http_client
        mock_client_class.return_value.__aexit__.return_value = None

        with patch(
            "src.writeback.servicenow_writeback.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            result = await client._patch(
                SYS_ID,
                {
                    "work_notes": "Internal note",
                },
            )

    assert result["ok"] is False
    assert "ServiceNow request failed" in result["error"]
    assert mock_http_client.patch.await_count == 4
    assert mock_sleep.await_count == 3


@pytest.mark.asyncio
async def test_patch_uses_correct_incident_url_and_headers(client):
    response = make_response(200)

    mock_http_client = AsyncMock()
    mock_http_client.patch.return_value = response

    with patch(
        "src.writeback.servicenow_writeback.httpx.AsyncClient"
    ) as mock_client_class:
        mock_client_class.return_value.__aenter__.return_value = mock_http_client
        mock_client_class.return_value.__aexit__.return_value = None

        result = await client._patch(
            SYS_ID,
            {
                "work_notes": "Internal note",
            },
        )

    assert result == {"ok": True}

    mock_http_client.patch.assert_awaited_once_with(
        url=f"{BASE_URL}/api/now/table/incident/{SYS_ID}",
        json={
            "work_notes": "Internal note",
        },
        auth=(USERNAME, PASSWORD),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )


# ---------------------------------------------------------------------------
# Security / isolation guarantees
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_suggest_does_not_write_customer_comments(client):
    with patch.object(
        client,
        "_patch",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ) as mock_patch:
        await client.suggest(
            sys_id=SYS_ID,
            ai_suggested_response="Suggested answer",
            ai_confidence=0.9,
        )

    _, payload = mock_patch.await_args.args
    assert "comments" not in payload


@pytest.mark.asyncio
async def test_escalate_does_not_write_customer_comments(client):
    with patch.object(
        client,
        "_patch",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ) as mock_patch:
        await client.escalate(
            sys_id=SYS_ID,
            reason="Low confidence",
        )

    _, payload = mock_patch.await_args.args
    assert "comments" not in payload


@pytest.mark.asyncio
async def test_add_work_note_does_not_write_customer_comments(client):
    with patch.object(
        client,
        "_patch",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ) as mock_patch:
        await client.add_work_note(
            sys_id=SYS_ID,
            note="Internal only",
        )

    _, payload = mock_patch.await_args.args

    assert set(payload) == {"work_notes"}
    assert "comments" not in payload
    assert "state" not in payload
    assert "assigned_to" not in payload


# ---------------------------------------------------------------------------
# Validation is enforced through public methods
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_suggest_does_not_call_patch_when_validation_fails(client):
    with patch.object(
        client,
        "_patch",
        new_callable=AsyncMock,
    ) as mock_patch:
        result = await client.suggest(
            sys_id=SYS_ID,
            ai_suggested_response="",
            ai_confidence=0.8,
        )

    assert result["ok"] is False
    mock_patch.assert_not_awaited()


@pytest.mark.asyncio
async def test_escalate_does_not_call_patch_when_validation_fails(client):
    with patch.object(
        client,
        "_patch",
        new_callable=AsyncMock,
    ) as mock_patch:
        result = await client.escalate(
            sys_id=SYS_ID,
            reason=" ",
        )

    assert result["ok"] is False
    mock_patch.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_work_note_does_not_call_patch_when_validation_fails(
    client,
):
    with patch.object(
        client,
        "_patch",
        new_callable=AsyncMock,
    ) as mock_patch:
        result = await client.add_work_note(
            sys_id=SYS_ID,
            note="",
        )

    assert result["ok"] is False
    mock_patch.assert_not_awaited()


# ---------------------------------------------------------------------------
# Direct helper validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "sys_id",
    ["", " ", None, 0, False],
)
def test_validate_sys_id_rejects_invalid_values(sys_id):
    with pytest.raises(
        ValueError,
        match="sys_id must be a non-empty string",
    ):
        ServiceNowWritebackClient._validate_sys_id(sys_id)


@pytest.mark.parametrize(
    "value,field_name",
    [
        ("", "note"),
        (" ", "note"),
        (None, "note"),
        (123, "note"),
        (False, "note"),
        ("", "reason"),
        (" ", "reason"),
        (None, "reason"),
        ("", "ai_suggested_response"),
        (" ", "ai_suggested_response"),
        (None, "ai_suggested_response"),
    ],
)
def test_validate_text_rejects_invalid_values(value, field_name):
    with pytest.raises(
        ValueError,
        match=f"{field_name} must be a non-empty string",
    ):
        ServiceNowWritebackClient._validate_text(
            value,
            field_name,
        )


@pytest.mark.parametrize(
    "confidence",
    [True, False, None, "0.5", object()],
)
def test_validate_confidence_rejects_non_numeric_values(confidence):
    with pytest.raises(
        ValueError,
        match="ai_confidence must be a number",
    ):
        ServiceNowWritebackClient._validate_confidence(confidence)


@pytest.mark.parametrize(
    "confidence",
    [-0.1, 1.1, -100, 100],
)
def test_validate_confidence_rejects_out_of_range_values(confidence):
    with pytest.raises(
        ValueError,
        match="ai_confidence must be between 0.0 and 1.0",
    ):
        ServiceNowWritebackClient._validate_confidence(confidence)


@pytest.mark.parametrize(
    "confidence",
    [0, 0.0, 0.5, 1, 1.0],
)
def test_validate_confidence_accepts_boundary_values(confidence):
    ServiceNowWritebackClient._validate_confidence(confidence)
