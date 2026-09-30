import asyncio

from agent.ports import WriteBackPort
from src.writeback.agent_adapter import ServiceNowWritebackAdapter


class FakeServiceNowClient:
    """Async fake client used to test the adapter without network access."""

    def __init__(self):
        self.calls = []

    async def add_work_note(self, sys_id, note):
        self.calls.append(
            {
                "operation": "add_work_note",
                "sys_id": sys_id,
                "note": note,
            }
        )
        return {"ok": True}

    async def suggest(
        self,
        sys_id,
        ai_suggested_response,
        ai_confidence,
    ):
        self.calls.append(
            {
                "operation": "suggest",
                "sys_id": sys_id,
                "ai_suggested_response": ai_suggested_response,
                "ai_confidence": ai_confidence,
            }
        )
        return {"ok": True}

    async def escalate(self, sys_id, reason, ai_confidence=None):
        self.calls.append(
            {
                "operation": "escalate",
                "sys_id": sys_id,
                "reason": reason,
                "ai_confidence": ai_confidence,
            }
        )
        return {"ok": True}


class FailingServiceNowClient:
    """Async fake client that simulates a ServiceNow failure."""

    async def add_work_note(self, sys_id, note):
        return {
            "ok": False,
            "error": "ServiceNow request failed",
        }

    async def suggest(
        self,
        sys_id,
        ai_suggested_response,
        ai_confidence,
    ):
        return {
            "ok": False,
            "error": "ServiceNow request failed",
        }

    async def escalate(self, sys_id, reason, ai_confidence=None):
        return {
            "ok": False,
            "error": "ServiceNow request failed",
        }


def test_adapter_implements_writeback_port():
    adapter = ServiceNowWritebackAdapter(
        client=FakeServiceNowClient(),
    )

    assert isinstance(adapter, WriteBackPort)


def test_add_work_note_forwards_only_required_arguments():
    client = FakeServiceNowClient()
    adapter = ServiceNowWritebackAdapter(client=client)

    result = adapter.add_work_note(
        sys_id="incident-sys-id",
        number="INC0010001",
        note="Internal investigation note",
    )

    assert result == {
        "ok": True,
        "status": "success",
    }

    assert client.calls == [
        {
            "operation": "add_work_note",
            "sys_id": "incident-sys-id",
            "note": "Internal investigation note",
        }
    ]


def test_suggest_forwards_only_s3_6_fields():
    client = FakeServiceNowClient()
    adapter = ServiceNowWritebackAdapter(client=client)

    result = adapter.suggest(
        sys_id="incident-sys-id",
        number="INC0010001",
        payload={
            "ai_suggested_response": "Restart the affected service.",
            "ai_confidence": 0.87,
            "human_review_required": True,
            "escalated": False,
            "citations": ["KB001"],
            "steps_count": 3,
        },
    )

    assert result == {
        "ok": True,
        "status": "success",
    }

    assert client.calls == [
        {
            "operation": "suggest",
            "sys_id": "incident-sys-id",
            "ai_suggested_response": "Restart the affected service.",
            "ai_confidence": 0.87,
        }
    ]


def test_escalate_forwards_sys_id_and_reason():
    client = FakeServiceNowClient()
    adapter = ServiceNowWritebackAdapter(client=client)

    result = adapter.escalate(
        sys_id="incident-sys-id",
        number="INC0010001",
        reason="AI confidence is below the escalation threshold.",
        payload={
            "ai_suggested_response": "Escalate to human support.",
            "ai_confidence": 0.35,
            "human_review_required": True,
            "escalated": True,
        },
    )

    assert result == {
        "ok": True,
        "status": "success",
    }

    assert client.calls == [
        {
            "operation": "escalate",
            "sys_id": "incident-sys-id",
            "reason": "AI confidence is below the escalation threshold.",
            "ai_confidence": 0.35,
        }
    ]


def test_adapter_translates_service_now_failure_to_agent_error():
    adapter = ServiceNowWritebackAdapter(
        client=FailingServiceNowClient(),
    )

    result = adapter.add_work_note(
        sys_id="incident-sys-id",
        number="INC0010001",
        note="Internal note",
    )

    assert result == {
        "ok": False,
        "error": "ServiceNow request failed",
        "status": "error",
        "success": False,
    }


def test_suggest_rejects_missing_response_before_client_call():
    client = FakeServiceNowClient()
    adapter = ServiceNowWritebackAdapter(client=client)

    result = adapter.suggest(
        sys_id="incident-sys-id",
        number="INC0010001",
        payload={
            "ai_confidence": 0.8,
        },
    )

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["success"] is False
    assert "ai_suggested_response must be a string" in result["error"]
    assert client.calls == []


def test_suggest_rejects_invalid_confidence_before_client_call():
    client = FakeServiceNowClient()
    adapter = ServiceNowWritebackAdapter(client=client)

    result = adapter.suggest(
        sys_id="incident-sys-id",
        number="INC0010001",
        payload={
            "ai_suggested_response": "Suggested resolution",
            "ai_confidence": "0.8",
        },
    )

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["success"] is False
    assert "ai_confidence must be a number" in result["error"]
    assert client.calls == []


def test_run_async_works_without_active_event_loop():
    async def sample():
        return {"ok": True}

    result = ServiceNowWritebackAdapter._run_async(sample())

    assert result == {"ok": True}


def test_adapter_does_not_make_network_requests():
    client = FakeServiceNowClient()
    adapter = ServiceNowWritebackAdapter(client=client)

    adapter.add_work_note(
        sys_id="incident-sys-id",
        number="INC0010001",
        note="No network call",
    )

    assert len(client.calls) == 1


def test_sync_agent_contract_can_call_all_three_operations():
    client = FakeServiceNowClient()
    adapter = ServiceNowWritebackAdapter(client=client)

    work_note_result = adapter.add_work_note(
        sys_id="sys-id",
        number="INC0010001",
        note="Work note",
    )

    suggest_result = adapter.suggest(
        sys_id="sys-id",
        number="INC0010001",
        payload={
            "ai_suggested_response": "Suggested response",
            "ai_confidence": 0.9,
        },
    )

    escalate_result = adapter.escalate(
        sys_id="sys-id",
        number="INC0010001",
        reason="Low confidence",
        payload={},
    )

    assert work_note_result["status"] == "success"
    assert suggest_result["status"] == "success"
    assert escalate_result["status"] == "success"

    assert [call["operation"] for call in client.calls] == [
        "add_work_note",
        "suggest",
        "escalate",
    ]