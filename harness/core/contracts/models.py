"""Versioned, strict contracts shared across harness modules."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .redaction import redact, redact_text


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


class NoOp(StrictContract):
    module_id: str
    reason: str
    capability: str


class ErrorEnvelope(StrictContract):
    code: str
    category: str
    severity: str
    retryable: bool
    module_id: str
    run_id: str
    plan_revision: int = Field(ge=1)
    step_id: str | None = None
    safe_message: str
    cause_ref: str | None = None

    @field_validator("safe_message", mode="before")
    @classmethod
    def redact_safe_message(cls, value: object) -> str:
        return redact_text(str(value))


class ArtifactEnvelope(StrictContract):
    artifact_id: str
    type: str
    content_hash: str
    producer: str
    input_refs: list[str]
    created_at: datetime
    classification: ArtifactClassification
    revision: int = Field(ge=1)


class IdempotencyKey(StrictContract):
    run_id: str
    plan_revision: int = Field(ge=1)
    step_id: str
    input_fingerprint: str


class TraceEvent(StrictContract):
    event_id: str
    event_type: TraceEventType
    run_id: str
    plan_revision: int = Field(ge=1)
    step_id: str | None = None
    timestamp: datetime
    input_refs: list[str]
    result_summary: dict[str, Any] | list[Any] | str
    duration_ms: int = Field(ge=0)
    classification: ArtifactClassification

    @field_validator("result_summary", mode="before")
    @classmethod
    def redact_result_summary(cls, value: object) -> object:
        return redact(value)


class PlanStep(StrictContract):
    step_id: str
    type: str
    depends_on: list[str]
    platform_scope: list[str]
    input_fingerprint: str
    required_capabilities: list[str] | None = None
    metric_refs: list[str] | None = None
    rule_packs: list[str] | None = None
    on_unsupported: Literal["await_alignment", "skip_optional"] | None = None


class Plan(StrictContract):
    plan_revision: int = Field(ge=1)
    target_platforms: list[str] = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    outline: list[str] = Field(min_length=1)
    steps: list[PlanStep] = Field(min_length=1)

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
    organization_id: str
    profile_version: str
    fingerprint: str
    approver: str
    approved_at: datetime
    scope: Literal["c1", "c2", "c3"]


class SourceManifestEntry(StrictContract):
    source_id: str
    platform: str
    account_id: str
    logical_connection: str
    adapter_id: str
    adapter_contract_version: str
    schema_fingerprint: str
    query_hash: str
    row_count: int = Field(ge=0)
    time_range_start: datetime | None = None
    time_range_end: datetime | None = None
    report_cutoff: datetime | None = None
    latency_window_seconds: int | None = Field(default=None, ge=0)
    watermark: datetime | None = None
    snapshot_hash: str
    completeness: DataCompleteness
    capabilities: list[str]


class SourceManifest(StrictContract):
    run_id: str
    plan_revision: int = Field(ge=1)
    sources: list[SourceManifestEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_sources(self) -> SourceManifest:
        ids = [source.source_id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate source_id")
        return self
