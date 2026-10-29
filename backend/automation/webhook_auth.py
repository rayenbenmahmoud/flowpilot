"""HMAC verification for inbound webhooks (the same scheme Stripe and GitHub use)."""

import hashlib
import hmac
import time

from .exceptions import ApiError


def sign(secret: str, timestamp: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(
    *, secret: str, timestamp: str | None, signature: str | None, body: bytes, tolerance: int, now: float | None = None
) -> None:
    if not secret:
        raise ApiError(
            503, "webhook_not_configured", "The server has no webhook secret configured, so webhooks are refused."
        )
    if not timestamp or not signature:
        raise ApiError(401, "missing_signature", "Send X-FlowPilot-Timestamp and X-FlowPilot-Signature headers.")
    try:
        sent_at = int(timestamp)
    except ValueError:
        raise ApiError(401, "invalid_timestamp", "X-FlowPilot-Timestamp must be unix seconds.") from None
    if abs((now if now is not None else time.time()) - sent_at) > tolerance:
        raise ApiError(
            401,
            "stale_timestamp",
            f"The timestamp is more than {tolerance} seconds away from server time (replay protection).",
        )
    if not hmac.compare_digest(sign(secret, timestamp, body), signature.strip()):
        raise ApiError(401, "invalid_signature", "The signature does not match the request body.")
