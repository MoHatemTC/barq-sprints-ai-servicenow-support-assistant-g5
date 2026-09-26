import asyncio
import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()


class ServiceNowWritebackClient:
    """
    Safe write-back client for ServiceNow incidents.

    This client is intentionally restricted to AI-related fields and
    internal work notes. It cannot update arbitrary Incident fields.
    """

    ALLOWED_FIELDS = frozenset(
        {
            "x_2216229_sprint_1_ai_status",
            "x_2216229_sprint_1_ai_confidence",
            "x_2216229_sprint_1_ai_suggested_response",
            "x_2216229_sprint_1_human_review_required",
            "x_2216229_sprint_1_ai_processed",
            "work_notes",
        }
    )

    TRANSIENT_STATUS_CODES = frozenset(
        {
            429,
            500,
            502,
            503,
            504,
        }
    )

    def __init__(
        self,
        instance_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.instance_url = (
            instance_url
            if instance_url is not None
            else os.getenv("SERVICENOW_INSTANCE_URL", "")
        ).rstrip("/")

        self.username = (
            username
            if username is not None
            else os.getenv("SERVICENOW_USERNAME")
        )

        self.password = (
            password
            if password is not None
            else os.getenv("SERVICENOW_PASSWORD")
        )

        self.timeout = (
            timeout
            if timeout is not None
            else float(
                os.getenv(
                    "SERVICENOW_WRITEBACK_TIMEOUT",
                    "10",
                )
            )
        )

        self.max_retries = (
            max_retries
            if max_retries is not None
            else int(
                os.getenv(
                    "SERVICENOW_WRITEBACK_MAX_RETRIES",
                    "3",
                )
            )
        )

        if not self.instance_url:
            raise ValueError(
                "SERVICENOW_INSTANCE_URL is not configured."
            )

        if not self.username:
            raise ValueError(
                "SERVICENOW_USERNAME is not configured."
            )

        if not self.password:
            raise ValueError(
                "SERVICENOW_PASSWORD is not configured."
            )

        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")

        if self.timeout <= 0:
            raise ValueError("timeout must be > 0")

    def _incident_url(self, sys_id: str) -> str:
        return (
            f"{self.instance_url}"
            f"/api/now/table/incident/{sys_id}"
        )

    @staticmethod
    def _validate_sys_id(sys_id: str) -> None:
        if not isinstance(sys_id, str) or not sys_id.strip():
            raise ValueError(
                "sys_id must be a non-empty string."
            )

    @staticmethod
    def _validate_text(
        value: str,
        field_name: str,
    ) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{field_name} must be a non-empty string."
            )

    @staticmethod
    def _validate_confidence(
        ai_confidence: float,
    ) -> None:
        if isinstance(ai_confidence, bool):
            raise ValueError(
                "ai_confidence must be a number."
            )

        if not isinstance(ai_confidence, (int, float)):
            raise ValueError(
                "ai_confidence must be a number."
            )

        if not 0.0 <= float(ai_confidence) <= 1.0:
            raise ValueError(
                "ai_confidence must be between 0.0 and 1.0."
            )

    @classmethod
    def _validate_payload(
        cls,
        payload: dict[str, Any],
    ) -> None:
        """
        Structural allow-list enforcement.

        Any field outside ALLOWED_FIELDS is rejected before the HTTP
        request is made.
        """

        unauthorized = set(payload) - cls.ALLOWED_FIELDS

        if unauthorized:
            raise ValueError(
                "Unauthorized ServiceNow fields: "
                + ", ".join(sorted(unauthorized))
            )

    async def _patch(
        self,
        sys_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Perform one logical PATCH operation with bounded retries.

        Expected validation and HTTP failures are converted into:

            {"ok": False, "error": "..."}

        rather than escaping to the caller.
        """

        try:
            self._validate_sys_id(sys_id)
            self._validate_payload(payload)

        except ValueError as exc:
            return {
                "ok": False,
                "error": str(exc),
            }

        url = self._incident_url(sys_id)

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        timeout = httpx.Timeout(
            self.timeout,
            connect=min(5.0, self.timeout),
        )

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=timeout
                ) as client:
                    response = await client.patch(
                        url=url,
                        json=payload,
                        auth=(self.username, self.password),
                        headers=headers,
                    )

                if response.is_success:
                    return {"ok": True}

                if response.status_code in self.TRANSIENT_STATUS_CODES:
                    if attempt < self.max_retries:
                        await asyncio.sleep(2**attempt)
                        continue

                    return {
                        "ok": False,
                        "error": (
                            "ServiceNow transient HTTP error "
                            f"{response.status_code} after "
                            f"{self.max_retries + 1} attempts."
                        ),
                    }

                return {
                    "ok": False,
                    "error": (
                        "ServiceNow HTTP error "
                        f"{response.status_code}."
                    ),
                }

            except (
                httpx.TimeoutException,
                httpx.NetworkError,
            ) as exc:
                if attempt < self.max_retries:
                    await asyncio.sleep(2**attempt)
                    continue

                return {
                    "ok": False,
                    "error": (
                        f"ServiceNow request failed: {exc}"
                    ),
                }

            except httpx.HTTPError as exc:
                return {
                    "ok": False,
                    "error": (
                        f"ServiceNow HTTP error: {exc}"
                    ),
                }

        return {
            "ok": False,
            "error": "ServiceNow request failed.",
        }

    async def add_work_note(
        self,
        sys_id: str,
        note: str,
    ) -> dict[str, Any]:
        """
        Add an internal ServiceNow work note.

        IMPORTANT:
        This method only writes to work_notes.
        It never writes to customer-facing comments.
        """

        try:
            self._validate_sys_id(sys_id)
            self._validate_text(note, "note")

            payload = {
                "work_notes": note.strip(),
            }

            return await self._patch(
                sys_id,
                payload,
            )

        except ValueError as exc:
            return {
                "ok": False,
                "error": str(exc),
            }

    async def suggest(
        self,
        sys_id: str,
        ai_suggested_response: str,
        ai_confidence: float,
    ) -> dict[str, Any]:
        """
        Write an AI suggestion to an Incident.

        The operation is represented by ONE atomic PATCH request.
        """

        try:
            self._validate_sys_id(sys_id)

            self._validate_text(
                ai_suggested_response,
                "ai_suggested_response",
            )

            self._validate_confidence(
                ai_confidence
            )

            payload = {
                "x_2216229_sprint_1_ai_status": "suggested",
                "x_2216229_sprint_1_ai_suggested_response": (
                    ai_suggested_response.strip()
                ),
                "x_2216229_sprint_1_ai_confidence": float(
                    ai_confidence
                ),
                "x_2216229_sprint_1_human_review_required": True,
                "x_2216229_sprint_1_ai_processed": True,
            }

            return await self._patch(
                sys_id,
                payload,
            )

        except ValueError as exc:
            return {
                "ok": False,
                "error": str(exc),
            }

    async def escalate(
        self,
        sys_id: str,
        reason: str,
    ) -> dict[str, Any]:
        """
        Escalate an Incident.

        The escalation reason is written only as an
        internal work note.
        """

        try:
            self._validate_sys_id(sys_id)

            self._validate_text(
                reason,
                "reason",
            )

            payload = {
                "x_2216229_sprint_1_ai_status": "escalated",
                "x_2216229_sprint_1_ai_suggested_response": "",
                "x_2216229_sprint_1_human_review_required": False,
                "work_notes": (
                    "AI escalation reason: "
                    f"{reason.strip()}"
                ),
            }

            return await self._patch(
                sys_id,
                payload,
            )

        except ValueError as exc:
            return {
                "ok": False,
                "error": str(exc),
            }
