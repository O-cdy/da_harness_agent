"""Ports that stay disabled until their own ADR."""

from __future__ import annotations

from harness.core.contracts.models import NoOp


def disabled(module_id: str, capability: str) -> NoOp:
    """Return a structured NoOp. No storage or network client is constructed."""
    return NoOp(
        module_id=module_id,
        reason=f"{capability} is not enabled",
        capability=capability,
    )
