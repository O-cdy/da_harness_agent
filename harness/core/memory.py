"""Read-only memory assembly. Previous metric numbers are not current facts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_METRIC_KEY = re.compile(r"^M\d+")


class MemoryError(ValueError):
    """A memory read tried to reuse a prior period's measured values."""


def assemble(
    *,
    caliber_paths: list[Path],
    errors_index: Path,
    previous_metrics: dict[str, Any] | None = None,
    previous_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble caliber and error references. Prior evidence may carry a fingerprint only."""
    if previous_metrics or _contains_metric_value(previous_evidence):
        raise MemoryError("previous metric values cannot enter current facts")
    fingerprint = None
    if previous_evidence is not None:
        raw = previous_evidence.get("fingerprint")
        if raw is not None:
            fingerprint = str(raw)
            if not fingerprint.startswith("sha256:"):
                raise MemoryError("previous evidence fingerprint is not a content hash")
    return {
        "caliber_refs": [path.as_posix() for path in caliber_paths],
        "errors_index": errors_index.as_posix(),
        "previous_fingerprint": fingerprint,
        "previous_metric_values": {},
    }


def _contains_metric_value(value: Any, key: str | None = None) -> bool:
    if key is not None and _METRIC_KEY.match(key):
        return True
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, dict):
        return any(_contains_metric_value(item, str(name)) for name, item in value.items())
    if isinstance(value, list):
        return any(_contains_metric_value(item) for item in value)
    return False
