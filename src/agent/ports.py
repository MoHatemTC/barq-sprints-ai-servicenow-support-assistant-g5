"""src.agent.ports forwarding to Agent.ports."""

from Agent.ports import FakeWriteBackPort, WriteBackPort

__all__ = ["WriteBackPort", "FakeWriteBackPort"]
