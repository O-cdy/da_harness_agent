"""Seal a candidate package and render whatever outline the plan carries."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from harness.core.contracts.models import ErrorEnvelope


def seal(package: dict[str, Any]) -> dict[str, Any]:
    """Return an immutable copy and its content hash."""
    encoded = json.dumps(package, sort_keys=True, separators=(",", ":")).encode()
    return {
        "package": json.loads(encoded),
        "content_hash": "sha256:" + hashlib.sha256(encoded).hexdigest(),
    }


def evaluate(sealed: dict[str, Any]) -> dict[str, Any]:
    """Score only the sealed copy."""
    again = seal(sealed["package"])
    return {
        "passed": again["content_hash"] == sealed["content_hash"],
        "content_hash": sealed["content_hash"],
    }


def validate(sealed: dict[str, Any], *, blocking: bool) -> dict[str, Any]:
    """A blocking failure writes an envelope and does not render a report."""
    scored = evaluate(sealed)
    if blocking or not scored["passed"]:
        envelope = ErrorEnvelope(
            code="validation-failed",
            category="evaluation",
            severity="error",
            retryable=False,
            module_id="validator",
            run_id="run-1",
            plan_revision=1,
            safe_message="candidate package failed validation",
        )
        return {"report": None, "envelope": envelope.model_dump(mode="json")}
    return {"report": "allowed", "envelope": None, "content_hash": scored["content_hash"]}


def render(outline: list[str], numbers: dict[str, str]) -> dict[str, str]:
    """Render Markdown and HTML from the plan outline."""
    lines: list[str] = []
    for item in outline:
        value = numbers.get(item, "")
        if value.lstrip().startswith(("=", "+", "@")):
            raise ValueError("formula injection rejected")
        lines.append(f"## {item}\n\n{value}".rstrip())
    markdown = "\n\n".join(lines) + "\n"
    html = "".join(f"<section><h2>{item}</h2></section>" for item in outline)
    return {"markdown": markdown, "html": html}
