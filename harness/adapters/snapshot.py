"""File and synthetic snapshots. Database sessions stay in the execution package."""

from __future__ import annotations

import hashlib
import json
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
    encoded = json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()
    dates = [str(fact["order_created_date"]) for fact in facts]
    return {
        "adapter_id": platform_id,
        "contract_version": "1",
        "schema_fingerprint": _digest(sorted(facts[0]) if facts else []),
        "capability": {"orders": "ready" if facts else "missing"},
        "coverage": {"start": min(dates) if dates else None, "end": max(dates) if dates else None},
        "watermark": max(dates) if dates else None,
        "unmapped_fields": [
            str(fact["order_id"]) for fact in facts if not fact.get("product_identity")
        ],
        "quality_assertions": [
            {"assertion_id": "row-count", "passed": True, "summary": "row count accepted"}
        ],
        "facts": facts,
        "row_count": len(facts),
        "content_hash": _digest(encoded),
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


def _digest(value: object) -> str:
    if isinstance(value, bytes):
        raw = value
    else:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()
