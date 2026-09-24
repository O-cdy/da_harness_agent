"""Central redaction for contract-safe summaries and exceptions."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEY = re.compile(
    r"(?:secret|password|passwd|token|api[_-]?key|authorization|cookie|dsn|"
    r"email|phone|address|name|buyer|credential|private[_-]?key)",
    re.IGNORECASE,
)
_PATTERNS = (
    re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s]+", re.IGNORECASE),
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)"),
    re.compile(
        r"(?i)\b(?:secret|password|passwd|token|api[_-]?key|authorization|cookie|dsn)"
        r"\s*[:=]\s*[^,;\r\n]+"
    ),
    re.compile(
        r"(?i)\b(?:buyer[_-]?(?:name|account)|name|address|phone|email)"
        r"\s*[:=]\s*[^,;\r\n]+"
    ),
)


def redact_text(value: str) -> str:
    """Remove DSNs, credentials and common PII canaries from text."""
    redacted = value
    for pattern in _PATTERNS:
        redacted = pattern.sub(REDACTED, redacted)
    return redacted


def redact(value: Any) -> Any:
    """Recursively produce a safe, structure-preserving value."""
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if _SENSITIVE_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, bytes):
        return REDACTED
    if isinstance(value, Sequence):
        return [redact(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_text(repr(value))


def safe_repr(value: Any) -> str:
    """Return a redacted repr for logging boundaries."""
    return redact_text(repr(redact(value)))


def safe_exception(error: BaseException) -> str:
    """Return exception type plus redacted message, never raw arguments."""
    return f"{type(error).__name__}: {redact_text(str(error))}"
