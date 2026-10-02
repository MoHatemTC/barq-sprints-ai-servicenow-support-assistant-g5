"""src.agent.ports compatibility re-export for the canonical Agent ports module."""

from Agent.ports import FakeWriteBackPort, WriteBackPort

__all__ = ["WriteBackPort", "FakeWriteBackPort"]
