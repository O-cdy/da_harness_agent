"""Model port. No key means no network call and no raw row leaves the process."""

from __future__ import annotations

import hashlib
import json

from harness.core.contracts.models import NoOp


class LlmError(ValueError):
    """A completion requested data the allowlist does not permit to leave."""


def complete(
    *,
    api_key: str | None,
    messages: list[dict[str, str]],
    allowlist: set[str],
) -> NoOp | dict[str, str]:
    """Return a NoOp without a key. Refuse fields outside the allowlist."""
    if not api_key:
        return NoOp(module_id="llm", reason="model key is absent", capability="completion")
    for message in messages:
        for key in message:
            if key == "role":
                continue
            if key not in allowlist:
                raise LlmError("field is outside the egress allowlist")
    payload = json.dumps(messages, sort_keys=True).encode()
    digest = hashlib.sha256(payload).hexdigest()
    return {"prompt_hash": f"sha256:{digest}", "response_hash": f"sha256:response-{digest[:12]}"}
