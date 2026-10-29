"""Mask secret-looking values before anything is stored or logged."""

import re
from typing import Any

SENSITIVE_KEY = re.compile(r"(secret|password|passwd|token|authorization|api[_-]?key|signature|credential)", re.I)
REDACTED = "[REDACTED]"


def redact(value: Any, _depth: int = 0) -> Any:
    if _depth > 8:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        return {
            key: REDACTED if SENSITIVE_KEY.search(str(key)) else redact(item, _depth + 1) for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item, _depth + 1) for item in value]
    return value
