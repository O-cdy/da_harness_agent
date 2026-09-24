from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from harness.core.contracts.models import (
    REDACTED_CONTRACT_FIELDS,
    ApprovalRecord,
    ArtifactClassification,
    ArtifactEnvelope,
    ErrorEnvelope,
    IdempotencyKey,
    NoOp,
    Plan,
    PlanStep,
    QualityAssertion,
    SourceManifest,
    SourceManifestEntry,
    SourceReadiness,
    TraceEvent,
)


def test_all_contracts_reject_extra_fields_and_unknown_schema_versions() -> None:
    with pytest.raises(ValidationError):
        NoOp(module_id="llm", reason="disabled", capability="completion", extra_field=True)

    with pytest.raises(ValidationError):
        NoOp(schema_version=2, module_id="llm", reason="disabled", capability="completion")


def test_identifiers_and_fingerprints_preserve_distinct_numeric_values() -> None:
    first = IdempotencyKey(
        run_id="0001",
        plan_revision=1,
        step_id="00123",
        input_fingerprint="sha256:00123",
    )
    second = IdempotencyKey(
        run_id="0002",
        plan_revision=1,
        step_id="00124",
        input_fingerprint="sha256:00124",
    )

    assert first.run_id == "0001"
    assert first.step_id == "00123"
    assert first.input_fingerprint == "sha256:00123"
    assert first != second


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("module_id", "contains space"),
        ("module_id", "alice@example.com"),
        ("capability", "mysql://user:pass@host/db"),
    ],
)
def test_identifier_fields_reject_unstructured_or_sensitive_values(
    field: str,
    value: str,
) -> None:
    payload = {"module_id": "llm", "reason": "disabled", "capability": "completion"}
    payload[field] = value
    with pytest.raises(ValidationError):
        NoOp(**payload)

    with pytest.raises(ValidationError):
        IdempotencyKey(
            run_id="run-1",
            plan_revision=1,
            step_id="step-1",
            input_fingerprint="not-a-sha256-fingerprint",
        )


def test_only_declared_free_content_fields_are_redacted() -> None:
    assert (
        frozenset(
            {
                "ArtifactEnvelope.input_refs",
                "ErrorEnvelope.cause_ref",
                "ErrorEnvelope.safe_message",
                "NoOp.reason",
                "Plan.acceptance_criteria",
                "Plan.outline",
                "QualityAssertion.summary",
                "TraceEvent.input_refs",
                "TraceEvent.result_summary",
            }
        )
        == REDACTED_CONTRACT_FIELDS
    )
    noop = NoOp(
        module_id="module-00123",
        reason="token=super-secret",
        capability="capability-00123",
    )

    assert noop.module_id == "module-00123"
    assert noop.capability == "capability-00123"
    assert noop.reason == "[REDACTED]"


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


def test_skip_optional_requires_existing_waiver_and_core_cannot_be_waived() -> None:
    common = {
        "step_id": "optional",
        "type": "noop",
        "depends_on": [],
        "platform_scope": ["example"],
        "input_fingerprint": "sha256:optional",
        "required_capabilities": ["identity"],
    }
    with pytest.raises(ValidationError, match="waiver"):
        PlanStep(
            **common,
            capability_class="optional",
            on_unsupported="skip_optional",
        )
    with pytest.raises(ValidationError):
        PlanStep(
            **common,
            capability_class="optional",
            on_unsupported="skip_optional",
            waiver_ref="",
        )

    accepted = PlanStep(
        **common,
        capability_class="optional",
        on_unsupported="skip_optional",
        waiver_ref="approval:waiver-1",
    )
    assert accepted.waiver_ref == "approval:waiver-1"

    with pytest.raises(ValidationError, match="core"):
        PlanStep(
            **common,
            capability_class="core",
            on_unsupported="skip_optional",
            waiver_ref="approval:waiver-1",
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


def test_all_free_text_references_use_central_redaction() -> None:
    error = ErrorEnvelope(
        code="E_RUNTIME",
        category="runtime",
        severity="error",
        retryable=False,
        module_id="executor",
        run_id="run-1",
        plan_revision=1,
        safe_message="safe",
        cause_ref="mysql://alice:secret@db.internal/prod",
    )
    trace = TraceEvent(
        event_id="event-1",
        event_type="tool",
        run_id="run-1",
        plan_revision=1,
        timestamp=datetime.now(UTC),
        input_refs=[
            "token=super-secret",
            "alice@example.com",
            "+1 555 123 4567",
        ],
        result_summary={"nested": ["mysql://alice:secret@host/db"]},
        duration_ms=1,
        classification=ArtifactClassification.INTERNAL,
    )

    dumped = f"{error.model_dump_json()} {trace.model_dump_json()}"
    for canary in (
        "mysql://",
        "super-secret",
        "alice@example.com",
        "555 123 4567",
    ):
        assert canary not in dumped


def test_formal_source_readiness_requires_complete_evidence() -> None:
    common = {
        "source_id": "source-1",
        "platform": "example",
        "account_id": "account-1",
        "logical_connection": "primary",
        "adapter_id": "adapter",
        "adapter_contract_version": "1",
        "schema_fingerprint": "sha256:schema",
        "query_hash": "sha256:query",
        "row_count": 1,
        "snapshot_hash": "sha256:snapshot",
        "completeness": "final",
        "capabilities": ["orders"],
    }
    with pytest.raises(ValidationError, match="formal readiness"):
        SourceManifestEntry(**common, readiness=SourceReadiness.READY)

    ready = SourceManifestEntry(
        **common,
        readiness=SourceReadiness.READY,
        time_range_start=datetime(2026, 8, 1, tzinfo=UTC),
        time_range_end=datetime(2026, 8, 31, tzinfo=UTC),
        report_cutoff=datetime(2026, 8, 31, tzinfo=UTC),
        latency_window_seconds=3600,
        watermark=datetime(2026, 9, 1, 1, tzinfo=UTC),
        quality_assertions=[
            QualityAssertion(assertion_id="row-count", passed=True, summary="rows valid")
        ],
    )
    assert ready.readiness is SourceReadiness.READY

    with pytest.raises(ValidationError, match="quality assertions"):
        SourceManifestEntry(
            **common,
            readiness=SourceReadiness.READY,
            time_range_start=datetime(2026, 8, 1, tzinfo=UTC),
            time_range_end=datetime(2026, 8, 31, tzinfo=UTC),
            report_cutoff=datetime(2026, 8, 31, tzinfo=UTC),
            latency_window_seconds=3600,
            watermark=datetime(2026, 9, 1, 1, tzinfo=UTC),
            quality_assertions=[
                QualityAssertion(
                    assertion_id="row-count",
                    passed=False,
                    summary="rows invalid",
                )
            ],
        )

    with pytest.raises(ValidationError, match="latency window"):
        SourceManifestEntry(
            **common,
            readiness=SourceReadiness.READY,
            time_range_start=datetime(2026, 8, 1, tzinfo=UTC),
            time_range_end=datetime(2026, 8, 31, tzinfo=UTC),
            report_cutoff=datetime(2026, 8, 31, tzinfo=UTC),
            latency_window_seconds=3600,
            watermark=datetime(2026, 8, 31, 0, 30, tzinfo=UTC),
            quality_assertions=[
                QualityAssertion(assertion_id="row-count", passed=True, summary="valid")
            ],
        )


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
