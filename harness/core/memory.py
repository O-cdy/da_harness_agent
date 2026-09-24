"""Read-only memory assembly. Previous metric numbers are not current facts."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class MemoryError(ValueError):
    """A memory read tried to reuse a prior period's measured values."""


def assemble(
    *,
    caliber_paths: list[Path],
    errors_index: Path,
    previous_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble caliber and error references without copying prior numbers."""
    if previous_metrics:
        raise MemoryError("previous metric values cannot enter current facts")
    return {
        "caliber_refs": [path.as_posix() for path in caliber_paths],
        "errors_index": errors_index.as_posix(),
        "previous_metric_values": {},
    }
