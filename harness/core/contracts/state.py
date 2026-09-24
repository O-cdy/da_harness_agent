"""Run lifecycle contract and its only legal transitions."""

from __future__ import annotations

from enum import StrEnum
from itertools import pairwise

from pydantic import Field, model_validator

from .models import DataCompleteness, ErrorEnvelope, StrictContract


class RunStatus(StrEnum):
    CREATED = "created"
    PLANNING = "planning"
    PLANNED = "planned"
    AWAITING_C1 = "awaiting_c1"
    PREPARING_SQL = "preparing_sql"
    AWAITING_C2 = "awaiting_c2"
    SNAPSHOTTING = "snapshotting"
    RUNNING = "running"
    VALIDATING = "validating"
    RENDERING = "rendering"
    SEALING = "sealing"
    EVALUATING = "evaluating"
    AWAITING_C3 = "awaiting_c3"
    COMPLETED = "completed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    FAILED = "failed"
    REVISION_REQUIRED = "revision_required"
    AWAITING_ALIGNMENT = "awaiting_alignment"
    WAITING_DATA = "waiting_data"


class ReportTier(StrEnum):
    DRY_RUN = "dry_run"
    FORMAL_PARTIAL = "formal_partial"
    FORMAL_FINAL = "formal_final"


class RunSnapshot(StrictContract):
    run_id: str
    plan_revision: int = Field(ge=1)
    revision: int = Field(ge=0)
    run_status: RunStatus
    data_completeness: DataCompleteness
    report_tier: ReportTier
    checkpoint: str | None = None
    resume_status: RunStatus | None = None
    error: ErrorEnvelope | None = None

    @model_validator(mode="after")
    def validate_state_details(self) -> RunSnapshot:
        paused = {RunStatus.AWAITING_ALIGNMENT, RunStatus.WAITING_DATA}
        if (self.run_status in paused) != (self.resume_status is not None):
            raise ValueError("paused status and resume_status must appear together")
        if self.run_status is RunStatus.FAILED and self.error is None:
            raise ValueError("failed run requires ErrorEnvelope")
        return self


class InvalidRunTransition(ValueError):
    """Raised when a caller attempts to bypass the run state machine."""


_MAINLINE = (
    RunStatus.CREATED,
    RunStatus.PLANNING,
    RunStatus.PLANNED,
    RunStatus.AWAITING_C1,
    RunStatus.PREPARING_SQL,
    RunStatus.AWAITING_C2,
    RunStatus.SNAPSHOTTING,
    RunStatus.RUNNING,
    RunStatus.VALIDATING,
    RunStatus.RENDERING,
    RunStatus.SEALING,
    RunStatus.EVALUATING,
    RunStatus.AWAITING_C3,
    RunStatus.COMPLETED,
)
_TRANSITIONS = {current: {following} for current, following in pairwise(_MAINLINE)}
_TRANSITIONS[RunStatus.CANCEL_REQUESTED] = {RunStatus.CANCELLED}
_TRANSITIONS[RunStatus.AWAITING_C3].add(RunStatus.REVISION_REQUIRED)
_TRANSITIONS[RunStatus.REVISION_REQUIRED] = {RunStatus.PLANNING}

_TERMINAL = {RunStatus.COMPLETED, RunStatus.CANCELLED, RunStatus.FAILED}
_PAUSED = {RunStatus.AWAITING_ALIGNMENT, RunStatus.WAITING_DATA}


def transition_run(
    snapshot: RunSnapshot,
    target: RunStatus,
    *,
    error: ErrorEnvelope | None = None,
) -> RunSnapshot:
    """Return the next immutable snapshot or reject the transition."""
    current = snapshot.run_status
    if current in _TERMINAL:
        raise InvalidRunTransition(f"illegal run transition: {current} -> {target}")

    updates: dict[str, object] = {"run_status": target, "error": error}
    if target is RunStatus.FAILED:
        if error is None:
            raise InvalidRunTransition("failed transition requires ErrorEnvelope")
        updates["resume_status"] = None
    elif target is RunStatus.CANCEL_REQUESTED:
        updates["resume_status"] = None
    elif current in _PAUSED:
        if target is not snapshot.resume_status:
            raise InvalidRunTransition(f"illegal run transition: {current} -> {target}")
        updates["resume_status"] = None
    elif target in _PAUSED:
        updates["resume_status"] = current
    elif target not in _TRANSITIONS.get(current, set()):
        raise InvalidRunTransition(f"illegal run transition: {current} -> {target}")

    if current is RunStatus.REVISION_REQUIRED and target is RunStatus.PLANNING:
        updates["plan_revision"] = snapshot.plan_revision + 1
        updates["checkpoint"] = None
    return snapshot.model_copy(update=updates)
