"""NoOp and error decisions for optional, required, and credential-gated capabilities."""

from __future__ import annotations

from harness.core.contracts.models import ErrorEnvelope, NoOp


def resolve_capability(
    *,
    capability: str,
    required: bool,
    enabled: bool,
    credentials_present: bool,
    run_id: str = "run-1",
    plan_revision: int = 1,
) -> NoOp | ErrorEnvelope | None:
    """Return NoOp, a blocking error, or None when the capability can run."""
    if not credentials_present and capability in {"db-read", "llm"}:
        return ErrorEnvelope(
            code="credentials-missing",
            category="preflight",
            severity="error",
            retryable=False,
            module_id="registry",
            run_id=run_id,
            plan_revision=plan_revision,
            safe_message="credentials are absent; the data path stays unchanged",
        )
    if enabled:
        return None
    if not required:
        return NoOp(
            module_id="registry",
            reason="optional capability is disabled",
            capability=capability,
        )
    return ErrorEnvelope(
        code="capability-missing",
        category="preflight",
        severity="error",
        retryable=False,
        module_id="registry",
        run_id=run_id,
        plan_revision=plan_revision,
        safe_message="required capability is unavailable",
    )
