"""Write-back port interface and offline fake implementation.

Defines the contract for outbound operations to ServiceNow (adding work notes,
suggesting resolutions, and escalating to human review) following the Ports &
Adapters / Hexagonal Architecture pattern.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class WriteBackPort(ABC):
    """Abstract port for ServiceNow write-back operations."""

    @abstractmethod
    def add_work_note(self, sys_id: str, number: str, note: str) -> Dict[str, Any]:
        """Post a work note to the incident."""
        pass

    @abstractmethod
    def suggest(self, sys_id: str, number: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Post a suggested resolution to the incident (pending human review)."""
        pass

    @abstractmethod
    def escalate(self, sys_id: str, number: str, reason: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Post an escalation to human review for the incident."""
        pass


class FakeWriteBackPort(WriteBackPort):
    """In-memory test double for offline unit testing without network or credentials."""

    def __init__(self, should_fail: bool = False, fail_error: Optional[str] = None):
        self.should_fail = should_fail
        self.fail_error = fail_error or "Simulated write-back port connection error"
        self.work_notes: List[Dict[str, Any]] = []
        self.suggestions: List[Dict[str, Any]] = []
        self.escalations: List[Dict[str, Any]] = []

    def add_work_note(self, sys_id: str, number: str, note: str) -> Dict[str, Any]:
        if self.should_fail:
            raise RuntimeError(self.fail_error)
        entry = {"sys_id": sys_id, "number": number, "note": note}
        self.work_notes.append(entry)
        return {"status": "success", "operation": "add_work_note", "entry": entry}

    def suggest(self, sys_id: str, number: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.should_fail:
            raise RuntimeError(self.fail_error)
        entry = {"sys_id": sys_id, "number": number, "payload": payload}
        self.suggestions.append(entry)
        return {"status": "success", "operation": "suggest", "entry": entry}

    def escalate(self, sys_id: str, number: str, reason: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.should_fail:
            raise RuntimeError(self.fail_error)
        entry = {"sys_id": sys_id, "number": number, "reason": reason, "payload": payload}
        self.escalations.append(entry)
        return {"status": "success", "operation": "escalate", "entry": entry}
