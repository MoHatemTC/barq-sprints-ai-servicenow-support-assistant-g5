import sys
from pathlib import Path

from dotenv import load_dotenv

# Make the project root importable when pytest runs.
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

# Load project environment variables before importing Worker.tasks.
load_dotenv()

import pytest

from Worker import tasks


WORKER_PAYLOAD = {
    "event_id": "event-123",
    "sys_id": "a" * 32,
    "number": "INC0010001",
    "received_at": "2026-09-25T20:00:00+00:00",
}


class FakeDB:
    """
    Small fake database used by the tests.

    It replaces the real database so the tests
    do not need PostgreSQL.
    """

    def __init__(self):
        self.completed = False
        self.status_updates = []

    async def is_event_completed(self, event_id):
        return self.completed

    async def mark_event_completed(self, event_id):
        self.completed = True
        return True

    async def update_event_status(self, event_id, status):
        self.status_updates.append(
            {
                "event_id": event_id,
                "status": status,
            }
        )


class FakeIncidentContext:
    """
    Minimal fake incident context returned by the
    security/guardrail stage.
    """

    original_number = "INC0010001"
    is_safe = True
    extracted_tags = []
    truncated_description = "test incident"


def test_worker_success(monkeypatch):
    """
    The worker should:
    1. Fetch the incident.
    2. Initialize the incident context.
    3. Call the configured handler.
    4. Mark the event as completed.
    """

    fake_db = FakeDB()

    async def fake_fetch_incident(sys_id):
        return {
            "sys_id": "a" * 32,
            "number": "INC0010001",
            "short_description": "Test incident",
            "description": "Test description",
        }

    async def fake_initialize_incident(
        payload,
        event_id,
    ):
        return FakeIncidentContext()

    monkeypatch.setattr(
        tasks,
        "db",
        fake_db,
    )

    monkeypatch.setattr(
        tasks,
        "fetch_incident",
        fake_fetch_incident,
    )

    monkeypatch.setattr(
        tasks,
        "initialize_incident",
        fake_initialize_incident,
    )

    monkeypatch.setattr(
        tasks,
        "incident_handler",
        lambda context: {
            "status": "processed",
            "number": context.original_number,
        },
    )

    result = tasks.process_incident_worker.run(
        WORKER_PAYLOAD
    )

    assert result["status"] == "processed"
    assert result["number"] == "INC0010001"
    assert fake_db.completed is True


def test_worker_retryable_error(monkeypatch):
    """
    A RetryableError should cause Celery to schedule
    another attempt.
    """

    fake_db = FakeDB()

    async def fake_fetch_incident(sys_id):
        raise tasks.RetryableError(
            "Temporary ServiceNow failure"
        )

    monkeypatch.setattr(
        tasks,
        "db",
        fake_db,
    )

    monkeypatch.setattr(
        tasks,
        "fetch_incident",
        fake_fetch_incident,
    )

    captured = {}

    def fake_retry(*args, **kwargs):
        captured["countdown"] = kwargs["countdown"]
        captured["exception"] = kwargs["exc"]

        # We don't actually want Celery to schedule
        # another task during the unit test.
        raise RuntimeError("retry scheduled")

    monkeypatch.setattr(
        tasks.process_incident_worker,
        "retry",
        fake_retry,
    )

    with pytest.raises(
        RuntimeError,
        match="retry scheduled",
    ):
        tasks.process_incident_worker.run(
            WORKER_PAYLOAD
        )

    assert captured["exception"] is not None
    assert captured["countdown"] >= 2


def test_worker_permanent_failure_goes_to_dlq(
    monkeypatch,
):
    """
    A PermanentError should skip retries and go
    directly to the Dead-Letter Queue.
    """

    fake_db = FakeDB()
    dlq_call = {}

    async def fake_fetch_incident(sys_id):
        raise tasks.PermanentError(
            "ServiceNow returned 404"
        )

    async def fake_on_dead_letter(
        event,
        error,
        attempts,
    ):
        dlq_call["event"] = event
        dlq_call["error"] = error
        dlq_call["attempts"] = attempts

    monkeypatch.setattr(
        tasks,
        "db",
        fake_db,
    )

    monkeypatch.setattr(
        tasks,
        "fetch_incident",
        fake_fetch_incident,
    )

    monkeypatch.setattr(
        tasks,
        "on_dead_letter",
        fake_on_dead_letter,
    )

    result = tasks.process_incident_worker.run(
        WORKER_PAYLOAD
    )

    assert result["status"] == "dead_lettered"
    assert result["attempts"] == 1

    assert dlq_call["event"] == WORKER_PAYLOAD
    assert isinstance(
        dlq_call["error"],
        tasks.PermanentError,
    )
    assert dlq_call["attempts"] == 1

    assert fake_db.status_updates[-1]["status"] == (
        "dead_lettered"
    )


def test_worker_retry_exhaustion_goes_to_dlq(
    monkeypatch,
):
    """
    When the maximum retry count is reached,
    the retryable error should go to the DLQ.

    max_retries = 2

    retries=0 -> attempt 1
    retries=1 -> attempt 2
    retries=2 -> attempt 3
    """

    fake_db = FakeDB()
    dlq_call = {}

    async def fake_fetch_incident(sys_id):
        raise tasks.RetryableError(
            "ServiceNow is temporarily unavailable"
        )

    async def fake_on_dead_letter(
        event,
        error,
        attempts,
    ):
        dlq_call["event"] = event
        dlq_call["error"] = error
        dlq_call["attempts"] = attempts

    monkeypatch.setattr(
        tasks,
        "db",
        fake_db,
    )

    monkeypatch.setattr(
        tasks,
        "fetch_incident",
        fake_fetch_incident,
    )

    monkeypatch.setattr(
        tasks,
        "on_dead_letter",
        fake_on_dead_letter,
    )

    # Create a Celery request context where
    # retries=2, which represents the third attempt.
    tasks.process_incident_worker.push_request(
        retries=2
    )

    try:
        result = tasks.process_incident_worker.run(
            WORKER_PAYLOAD
        )
    finally:
        tasks.process_incident_worker.pop_request()

    assert result["status"] == "dead_lettered"
    assert result["attempts"] == 3

    assert dlq_call["event"] == WORKER_PAYLOAD
    assert dlq_call["attempts"] == 3

    assert fake_db.status_updates[-1]["status"] == (
        "dead_lettered"
    )


def test_worker_skips_completed_event(monkeypatch):
    """
    A completed event must not be processed again.

    This verifies the independent completion marker.
    """

    fake_db = FakeDB()
    fake_db.completed = True

    monkeypatch.setattr(
        tasks,
        "db",
        fake_db,
    )

    result = tasks.process_incident_worker.run(
        WORKER_PAYLOAD
    )

    assert result["status"] == "already_completed"
    assert result["event_id"] == "event-123"
    assert result["sys_id"] == "a" * 32

