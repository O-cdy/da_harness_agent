from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from harness.core.contracts.models import (
    ApprovalRecord,
    ArtifactClassification,
    ArtifactEnvelope,
    ErrorEnvelope,
    NoOp,
    Plan,
    PlanStep,
    SourceManifest,
    SourceManifestEntry,
    TraceEvent,
)


def test_all_contracts_reject_extra_fields_and_unknown_schema_versions() -> None:
    with pytest.raises(ValidationError):
        NoOp(module_id="llm", reason="disabled", capability="completion", extra_field=True)

    with pytest.raises(ValidationError):
        NoOp(schema_version=2, module_id="llm", reason="disabled", capability="completion")


def test_plan_step_rejects_dangling_dependencies() -> None:
    step = PlanStep(
        step_id="render",
        type="noop",
        depends_on=["missing"],
        platform_scope=[],
        input_fingerprint="sha256:abc",
    )

    with pytest.raises(ValidationError, match="unknown step"):
        Plan(
            plan_revision=1,
            target_platforms=["example"],
            acceptance_criteria=["artifact exists"],
            outline=["result"],
            steps=[step],
        )


def test_plan_rejects_dependency_cycles() -> None:
    first = PlanStep(
        step_id="first",
        type="noop",
        depends_on=["second"],
        platform_scope=[],
        input_fingerprint="sha256:first",
    )
    second = PlanStep(
        step_id="second",
        type="noop",
        depends_on=["first"],
        platform_scope=[],
        input_fingerprint="sha256:second",
    )

    with pytest.raises(ValidationError, match="cycle"):
        Plan(
            plan_revision=1,
            target_platforms=["example"],
            acceptance_criteria=["artifact exists"],
            outline=["result"],
            steps=[first, second],
        )


def test_plan_rejects_duplicate_and_self_referencing_steps() -> None:
    step = PlanStep(
        step_id="same",
        type="noop",
        depends_on=[],
        platform_scope=[],
        input_fingerprint="sha256:same",
    )
    with pytest.raises(ValidationError, match="duplicate step_id"):
        Plan(
            plan_revision=1,
            target_platforms=["example"],
            acceptance_criteria=["done"],
            outline=["result"],
            steps=[step, step],
        )

    self_referencing = step.model_copy(update={"depends_on": ["same"]})
    with pytest.raises(ValidationError, match="depend on itself"):
        Plan(
            plan_revision=1,
            target_platforms=["example"],
            acceptance_criteria=["done"],
            outline=["result"],
            steps=[self_referencing],
        )


def test_sensitive_canaries_are_removed_from_safe_contract_fields() -> None:
    error = ErrorEnvelope(
        code="E_RUNTIME",
        category="runtime",
        severity="error",
        retryable=False,
        module_id="executor",
        run_id="run-1",
        plan_revision=1,
        step_id="step-1",
        safe_message=(
            "failed dsn=mysql://alice:secret@db.internal/prod "
            "email=alice@example.com token=super-secret"
        ),
        cause_ref="cause:sha256",
    )
    trace = TraceEvent(
        event_id="event-1",
        event_type="tool",
        run_id="run-1",
        plan_revision=1,
        step_id="step-1",
        timestamp=datetime.now(UTC),
        input_refs=["artifact:input"],
        result_summary={"buyer_email": "alice@example.com", "rows": 3},
        duration_ms=4,
        classification=ArtifactClassification.INTERNAL,
    )

    dumped = f"{error.model_dump_json()} {trace.model_dump_json()}"
    assert "secret" not in dumped
    assert "alice@example.com" not in dumped
    assert "mysql://" not in dumped
    assert "[REDACTED]" in dumped


def test_artifact_manifest_and_approval_contracts_are_strict() -> None:
    artifact = ArtifactEnvelope(
        artifact_id="artifact-1",
        type="json",
        content_hash="sha256:abc",
        producer="unit-test",
        input_refs=[],
        created_at=datetime.now(UTC),
        classification=ArtifactClassification.INTERNAL,
        revision=1,
    )
    manifest = SourceManifest(
        run_id="run-1",
        plan_revision=1,
        sources=[
            SourceManifestEntry(
                source_id="source-1",
                platform="example",
                account_id="account-1",
                logical_connection="primary",
                adapter_id="adapter",
                adapter_contract_version="1",
                schema_fingerprint="sha256:schema",
                query_hash="sha256:query",
                row_count=1,
                snapshot_hash="sha256:snapshot",
                completeness="final",
                capabilities=["orders"],
            )
        ],
    )
    approval = ApprovalRecord(
        organization_id="org-1",
        profile_version="1.0.0",
        fingerprint="sha256:approval",
        approver="reviewer",
        approved_at=datetime.now(UTC),
        scope="c1",
    )

    assert artifact.schema_version == manifest.schema_version == approval.schema_version == 1

    with pytest.raises(ValidationError, match="duplicate source_id"):
        SourceManifest(
            run_id="run-1",
            plan_revision=1,
            sources=[manifest.sources[0], manifest.sources[0]],
        )
