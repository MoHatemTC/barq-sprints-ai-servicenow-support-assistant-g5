"""Adapter between the synchronous agent WriteBackPort and S3.6 ServiceNow client."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

from agent.ports import WriteBackPort
from src.writeback.servicenow_writeback import ServiceNowWritebackClient


class ServiceNowWritebackAdapter(WriteBackPort):
    """Bridge the synchronous agent WriteBackPort to the async S3.6 client."""

    def __init__(
        self,
        client: ServiceNowWritebackClient | None = None,
    ) -> None:
        self.client = client or ServiceNowWritebackClient()

    @staticmethod
    def _run_async(coro: Any) -> Dict[str, Any]:
        """Run an async write-back operation from the synchronous agent tool."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        # The agent tool is synchronous, but it can be called while
        # the worker is already inside an active asyncio event loop.
        # Run the coroutine in a separate thread with its own event loop.
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()

    @staticmethod
    def _to_agent_result(result: Dict[str, Any]) -> Dict[str, Any]:
        """Translate the S3.6 {ok: bool} contract to the agent tool contract."""
        if result.get("ok") is True:
            return {
                **result,
                "status": "success",
            }

        return {
            **result,
            "status": "error",
            "success": False,
        }

    def add_work_note(
        self,
        sys_id: str,
        number: str,
        note: str,
    ) -> Dict[str, Any]:
        """Write an internal work note to the ServiceNow incident."""
        result = self._run_async(
            self.client.add_work_note(
                sys_id=sys_id,
                note=note,
            )
        )
        return self._to_agent_result(result)

    def suggest(
        self,
        sys_id: str,
        number: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Write the AI suggestion and confidence to ServiceNow."""
        ai_suggested_response = payload.get("ai_suggested_response")
        ai_confidence = payload.get("ai_confidence")

        if not isinstance(ai_suggested_response, str):
            return {
                "status": "error",
                "success": False,
                "ok": False,
                "error": "payload.ai_suggested_response must be a string.",
            }

        if isinstance(ai_confidence, bool) or not isinstance(
            ai_confidence, (int, float)
        ):
            return {
                "status": "error",
                "success": False,
                "ok": False,
                "error": "payload.ai_confidence must be a number.",
            }

        result = self._run_async(
            self.client.suggest(
                sys_id=sys_id,
                ai_suggested_response=ai_suggested_response,
                ai_confidence=float(ai_confidence),
            )
        )
        return self._to_agent_result(result)

    def escalate(
        self,
        sys_id: str,
        number: str,
        reason: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Escalate the incident to human review in ServiceNow."""
        result = self._run_async(
            self.client.escalate(
                sys_id=sys_id,
                reason=reason,
                ai_confidence=(payload or {}).get("ai_confidence"),
            )
        )
        return self._to_agent_result(result)