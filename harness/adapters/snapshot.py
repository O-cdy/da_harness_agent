"""Synthetic platform snapshots. No live database connection is opened here."""

from __future__ import annotations

from pathlib import Path

from harness.core.contracts.models import ErrorEnvelope


class AdapterError(ValueError):
    """A file or canonical snapshot violated an ingress guard."""


def require_credentials(present: bool, *, run_id: str = "run-1") -> ErrorEnvelope | None:
    """Fail closed when database credentials are absent."""
    if present:
        return None
    return ErrorEnvelope(
        code="credentials-missing",
        category="ingest",
        severity="error",
        retryable=False,
        module_id="adapter",
        run_id=run_id,
        plan_revision=1,
        safe_message="database credentials are absent; no alternate source was selected",
    )


def canonical_snapshot(platform_id: str, rows: list[dict[str, object]]) -> dict[str, object]:
    """Map already-synthetic rows into canonical order facts."""
    facts: list[dict[str, object]] = []
    for row in rows:
        facts.append(
            {
                "platform": platform_id,
                "order_id": str(row["order_id"]),
                "account_id": str(row.get("account_id", "account")),
                "order_created_date": str(row["order_created_date"]),
                "item_gross_amount": str(row["item_gross_amount"]),
                "seller_discount_amount": str(row.get("seller_discount_amount", "0")),
                "commercial_quantity": str(row.get("commercial_quantity", "1")),
                "product_identity": row.get("product_identity"),
                "channel": str(row.get("channel", "store")),
            }
        )
    return {
        "adapter_id": platform_id,
        "contract_version": "1",
        "facts": facts,
        "row_count": len(facts),
        "content_hash": f"sha256:{platform_id}-{len(facts)}",
    }


def read_delimited_file(path: Path, *, root: Path, max_bytes: int = 1_000_000) -> list[str]:
    """Read a small text table and reject traversal, size, and formula cells."""
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise AdapterError("file path escapes the input root")
    size = resolved.stat().st_size
    if size > max_bytes:
        raise AdapterError("file exceeds the configured size limit")
    text = resolved.read_text(encoding="utf-8")
    if "\x00" in text:
        raise AdapterError("malicious file content rejected")
    lines: list[str] = []
    for line in text.splitlines():
        if not line:
            continue
        cell = line.split(",")[0].lstrip()
        if cell.startswith(("=", "+", "@")):
            raise AdapterError("formula injection rejected")
        lines.append(line)
    return lines
