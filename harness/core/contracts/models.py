"""Versioned, strict contracts shared across harness modules."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .redaction import redact, redact_text

Identifier = Annotated[
    str,
    Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$"),
]
Reference = Annotated[
    str,
    Field(min_length=1, max_length=512, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$"),
]
Fingerprint = Annotated[
    str,
    Field(min_length=8, max_length=255, pattern=r"^sha256:[A-Za-z0-9._-]+$"),
]

REDACTED_CONTRACT_FIELDS = frozenset(
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


class StrictContract(BaseModel):
    """Base for immutable v1 contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1


class ArtifactClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class TraceEventType(StrEnum):
    STATE = "state"
    TOOL = "tool"
    POLICY = "policy"
    LLM = "llm"
    APPROVAL = "approval"
    ARTIFACT = "artifact"


class DataCompleteness(StrEnum):
    PARTIAL = "partial"
    FINAL = "final"


class SourceReadiness(StrEnum):
    NOT_READY = "not_ready"
    READY = "ready"


class NoOp(StrictContract):
    module_id: Identifier
    reason: str
    capability: Identifier

    @field_validator("reason", mode="before")
    @classmethod
    def redact_reason(cls, value: object) -> str:
        return redact_text(str(value))


class ErrorEnvelope(StrictContract):
    code: Identifier
    category: Identifier
    severity: Identifier
    retryable: bool
    module_id: Identifier
    run_id: Identifier
    plan_revision: int = Field(ge=1)
    step_id: Identifier | None = None
    safe_message: str
    cause_ref: str | None = None

    @field_validator("safe_message", "cause_ref", mode="before")
    @classmethod
    def redact_error_text(cls, value: object) -> str | None:
        if value is None:
            return None
        return redact_text(str(value))


class ArtifactEnvelope(StrictContract):
    artifact_id: Identifier
    type: Identifier
    content_hash: Fingerprint
    producer: Identifier
    input_refs: list[str]
    created_at: datetime
    classification: ArtifactClassification
    revision: int = Field(ge=1)

    @field_validator("input_refs", mode="before")
    @classmethod
    def redact_artifact_inputs(cls, value: object) -> object:
        return redact(value)


class IdempotencyKey(StrictContract):
    run_id: Identifier
    plan_revision: int = Field(ge=1)
    step_id: Identifier
    input_fingerprint: Fingerprint


class TraceEvent(StrictContract):
    event_id: Identifier
    event_type: TraceEventType
    run_id: Identifier
    plan_revision: int = Field(ge=1)
    step_id: Identifier | None = None
    timestamp: datetime
    input_refs: list[str]
    result_summary: dict[str, Any] | list[Any] | str
    duration_ms: int = Field(ge=0)
    classification: ArtifactClassification

    @field_validator("result_summary", mode="before")
    @classmethod
    def redact_result_summary(cls, value: object) -> object:
        return redact(value)

    @field_validator("input_refs", mode="before")
    @classmethod
    def redact_trace_inputs(cls, value: object) -> object:
        return redact(value)


class PlanStep(StrictContract):
    step_id: Identifier
    type: Identifier
    depends_on: list[Identifier]
    platform_scope: list[Identifier]
    input_fingerprint: Fingerprint
    required_capabilities: list[Identifier] | None = None
    metric_refs: list[Identifier] | None = None
    rule_packs: list[Reference] | None = None
    on_unsupported: Literal["await_alignment", "skip_optional"] | None = None
    capability_class: Literal["core", "optional"] | None = None
    waiver_ref: Reference | None = None

    @model_validator(mode="after")
    def validate_unsupported_policy(self) -> PlanStep:
        if self.capability_class == "core" and (
            self.waiver_ref is not None or self.on_unsupported == "skip_optional"
        ):
            raise ValueError("core capability cannot be waived")
        if self.on_unsupported == "skip_optional":
            if self.capability_class != "optional" or self.waiver_ref is None:
                raise ValueError("skip_optional requires existing optional capability waiver")
        elif self.waiver_ref is not None:
            raise ValueError("waiver_ref is only valid for skip_optional")
        return self


class Plan(StrictContract):
    plan_revision: int = Field(ge=1)
    target_platforms: list[Identifier] = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    outline: list[str] = Field(min_length=1)
    steps: list[PlanStep] = Field(min_length=1)

    @field_validator("acceptance_criteria", "outline", mode="before")
    @classmethod
    def redact_plan_text(cls, value: object) -> object:
        return redact(value)

    @model_validator(mode="after")
    def validate_dag(self) -> Plan:
        ids = [step.step_id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate step_id")
        known = set(ids)
        for step in self.steps:
            unknown = set(step.depends_on) - known
            if unknown:
                raise ValueError(f"unknown step dependencies: {sorted(unknown)}")
            if step.step_id in step.depends_on:
                raise ValueError("step cannot depend on itself")
        dependencies = {step.step_id: set(step.depends_on) for step in self.steps}
        while dependencies:
            ready = {step_id for step_id, needs in dependencies.items() if not needs}
            if not ready:
                raise ValueError("plan dependency cycle")
            dependencies = {
                step_id: needs - ready
                for step_id, needs in dependencies.items()
                if step_id not in ready
            }
        return self


class ApprovalRecord(StrictContract):
    organization_id: Identifier
    profile_version: Identifier
    fingerprint: Fingerprint
    approver: Identifier
    approved_at: datetime
    scope: Literal["c1", "c2", "c3"]


class QualityAssertion(StrictContract):
    assertion_id: Identifier
    passed: bool
    summary: str

    @field_validator("summary", mode="before")
    @classmethod
    def redact_summary(cls, value: object) -> str:
        return redact_text(str(value))


class SourceManifestEntry(StrictContract):
    source_id: Identifier
    platform: Identifier
    account_id: Identifier
    logical_connection: Identifier
    adapter_id: Identifier
    adapter_contract_version: Identifier
    schema_fingerprint: Fingerprint
    query_hash: Fingerprint
    row_count: int = Field(ge=0)
    time_range_start: datetime | None = None
    time_range_end: datetime | None = None
    report_cutoff: datetime | None = None
    latency_window_seconds: int | None = Field(default=None, ge=0)
    watermark: datetime | None = None
    snapshot_hash: Fingerprint
    completeness: DataCompleteness
    capabilities: list[Identifier]
    readiness: SourceReadiness = SourceReadiness.NOT_READY
    quality_assertions: list[QualityAssertion] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_readiness(self) -> SourceManifestEntry:
        if (
            self.time_range_start is not None
            and self.time_range_end is not None
            and self.time_range_end < self.time_range_start
        ):
            raise ValueError("source time range is reversed")
        if self.readiness is SourceReadiness.READY:
            required = (
                self.time_range_start,
                self.time_range_end,
                self.report_cutoff,
                self.latency_window_seconds,
                self.watermark,
            )
            if any(value is None for value in required):
                raise ValueError("formal readiness requires complete timing evidence")
            if not self.quality_assertions or not all(
                assertion.passed for assertion in self.quality_assertions
            ):
                raise ValueError("formal readiness requires passing quality assertions")
            cutoff = self.report_cutoff
            latency = self.latency_window_seconds
            watermark = self.watermark
            if cutoff is None or latency is None or watermark is None:
                raise ValueError("formal readiness requires complete timing evidence")
            ready_at = cutoff + timedelta(seconds=latency)
            if watermark < ready_at:
                raise ValueError("formal readiness watermark precedes latency window")
        return self


class SourceManifest(StrictContract):
    run_id: Identifier
    plan_revision: int = Field(ge=1)
    sources: list[SourceManifestEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_sources(self) -> SourceManifest:
        ids = [source.source_id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate source_id")
        return self
