import os
import hmac
import hashlib
import base64
import logging
from typing import Optional
from fastapi import Request, HTTPException, status, Header

logger = logging.getLogger("servicenow_webhook.auth")


def is_valid_servicenow_signature(body: bytes, incoming_signature: Optional[str], secret: str) -> bool:
    if not incoming_signature:
        return False

    if not secret:
        return False

    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    
    # --- أسطر جديدة لطباعة التوقيعات في نافذة السيرفر لمقارنتها ---
    expected_b64 = base64.b64encode(digest).decode("ascii")
    expected_hex = digest.hex()
    logger.warning("--- SIGNATURE DEBUG ---")
    logger.warning(f"1. Received from ServiceNow: {incoming_signature}")
    logger.warning(f"2. Python Expected (Base64): {expected_b64}")
    logger.warning(f"3. Python Expected (Hex): {expected_hex}")
    logger.warning(f"4. Raw Body Received: {body.decode('utf-8', errors='ignore')}")
    logger.warning("-----------------------")
    # -------------------------------------------------------------

    candidate_signatures = {
        expected_hex,
        expected_hex.upper(),
        expected_b64,
        expected_b64.upper(),
    }
    return any(
        hmac.compare_digest(candidate_signature, incoming_signature.strip())
        for candidate_signature in candidate_signatures
    )


async def verify_webhook_signature(
    request: Request,
    x_servicenow_signature: Optional[str] = Header(None, alias="X-ServiceNow-Signature")
):
    expected_secret = os.getenv("WEBHOOK_SECRET")

    if not expected_secret:
        logger.error("WEBHOOK_SECRET is not configured in the environment.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook security is not configured.",
        )

    if not x_servicenow_signature:
        logger.warning("Missing X-ServiceNow-Signature header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing signature header"
        )

    body = await request.body()

    if not is_valid_servicenow_signature(body, x_servicenow_signature, expected_secret):
        logger.warning(
            "Invalid webhook signature.",
            extra={"signature_prefix": x_servicenow_signature[:12]},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature"
        )

    return True