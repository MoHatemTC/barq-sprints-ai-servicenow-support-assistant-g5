"""src.agent.ports forwarding to agent.ports."""

from agent.ports import FakeWriteBackPort, WriteBackPort

__all__ = ["WriteBackPort", "FakeWriteBackPort"]
