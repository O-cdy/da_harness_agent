"""Run lifecycle contract and its only legal transitions."""

from __future__ import annotations

from enum import StrEnum
from itertools import pairwise

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

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


class BranchStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_ALIGNMENT = "awaiting_alignment"
    WAITING_DATA = "waiting_data"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BranchSnapshot(StrictContract):
    branch_id: str
    step_id: str
    status: BranchStatus
    checkpoint: str | None = None
    resume_status: BranchStatus | None = None

    @model_validator(mode="after")
    def validate_pause_details(self) -> BranchSnapshot:
        paused = {BranchStatus.AWAITING_ALIGNMENT, BranchStatus.WAITING_DATA}
        if self.status in paused:
            if self.resume_status not in {BranchStatus.PENDING, BranchStatus.RUNNING}:
                raise ValueError("paused branch requires active resume_status")
            if self.checkpoint is None:
                raise ValueError("paused branch requires checkpoint")
        elif self.resume_status is not None:
            raise ValueError("active or terminal branch cannot carry resume_status")
        return self


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
    branches: list[BranchSnapshot] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_state_details(self) -> RunSnapshot:
        paused = {RunStatus.AWAITING_ALIGNMENT, RunStatus.WAITING_DATA}
        if self.run_status in paused:
            if self.resume_status not in _RESUMABLE_RUN_STATUSES:
                raise ValueError("paused run requires active resume_status")
            if not self.checkpoint:
                raise ValueError("paused run requires committed checkpoint")
        elif self.resume_status is not None:
            raise ValueError("active or terminal run cannot carry resume_status")
        if self.run_status is RunStatus.FAILED:
            if self.error is None:
                raise ValueError("failed run requires ErrorEnvelope")
            if self.error.run_id != self.run_id:
                raise ValueError("ErrorEnvelope run_id must match snapshot")
            if self.error.plan_revision != self.plan_revision:
                raise ValueError("ErrorEnvelope plan_revision must match snapshot")
        elif self.error is not None:
            raise ValueError("only failed run may carry ErrorEnvelope")
        if (
            self.data_completeness is DataCompleteness.PARTIAL
            and self.report_tier is ReportTier.FORMAL_FINAL
        ):
            raise ValueError("partial data cannot be formal_final")
        branch_ids = [branch.branch_id for branch in self.branches]
        if len(branch_ids) != len(set(branch_ids)):
            raise ValueError("duplicate branch_id")
        runnable = {BranchStatus.PENDING, BranchStatus.RUNNING}
        if self.run_status in paused and any(branch.status in runnable for branch in self.branches):
            raise ValueError("paused run cannot contain runnable branch")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        schema = handler(core_schema)
        paused_values = sorted(status.value for status in _PAUSED)
        resumable_values = sorted(status.value for status in _RESUMABLE_RUN_STATUSES)
        schema.setdefault("allOf", []).append(
            {
                "if": {
                    "properties": {"run_status": {"enum": paused_values}},
                    "required": ["run_status"],
                },
                "then": {
                    "properties": {
                        "checkpoint": {"minLength": 1, "type": "string"},
                        "resume_status": {"enum": resumable_values},
                    },
                    "required": ["checkpoint", "resume_status"],
                },
                "else": {"properties": {"resume_status": {"type": "null"}}},
            }
        )
        return schema


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
_RESUMABLE_RUN_STATUSES = frozenset(
    {
        RunStatus.PLANNING,
        RunStatus.PREPARING_SQL,
        RunStatus.SNAPSHOTTING,
        RunStatus.RUNNING,
        RunStatus.VALIDATING,
        RunStatus.RENDERING,
        RunStatus.SEALING,
        RunStatus.EVALUATING,
    }
)
_BRANCH_PAUSED = {BranchStatus.AWAITING_ALIGNMENT, BranchStatus.WAITING_DATA}
_BRANCH_TRANSITIONS = {
    BranchStatus.PENDING: {BranchStatus.RUNNING, BranchStatus.CANCELLED},
    BranchStatus.RUNNING: {
        BranchStatus.AWAITING_ALIGNMENT,
        BranchStatus.WAITING_DATA,
        BranchStatus.COMPLETED,
        BranchStatus.FAILED,
        BranchStatus.CANCELLED,
    },
}


def transition_run(
    snapshot: RunSnapshot,
    target: RunStatus,
    *,
    checkpoint: str | None = None,
    error: ErrorEnvelope | None = None,
) -> RunSnapshot:
    """Return the next immutable snapshot or reject the transition."""
    current = snapshot.run_status
    if current in _TERMINAL:
        raise InvalidRunTransition(f"illegal run transition: {current} -> {target}")

    updates: dict[str, object] = {"run_status": target, "error": error}
    if current in _PAUSED:
        if target is RunStatus.CANCEL_REQUESTED:
            updates["resume_status"] = None
        elif target is not snapshot.resume_status or checkpoint != snapshot.checkpoint:
            raise InvalidRunTransition("paused run must resume from its committed checkpoint")
        else:
            updates["resume_status"] = None
            updates["checkpoint"] = snapshot.checkpoint
    elif target in _PAUSED:
        if current not in _RESUMABLE_RUN_STATUSES or not checkpoint:
            raise InvalidRunTransition("run pause requires active state and committed checkpoint")
        updates["resume_status"] = current
        updates["checkpoint"] = checkpoint
    elif target is RunStatus.FAILED:
        if error is None:
            raise InvalidRunTransition("failed transition requires ErrorEnvelope")
        updates["resume_status"] = None
    elif target is RunStatus.CANCEL_REQUESTED:
        updates["resume_status"] = None
    elif target not in _TRANSITIONS.get(current, set()):
        raise InvalidRunTransition(f"illegal run transition: {current} -> {target}")

    if current is RunStatus.REVISION_REQUIRED and target is RunStatus.PLANNING:
        updates["plan_revision"] = snapshot.plan_revision + 1
        updates["checkpoint"] = None
    return RunSnapshot.model_validate({**snapshot.model_dump(), **updates})


def transition_branch(
    snapshot: RunSnapshot,
    branch_id: str,
    target: BranchStatus,
    *,
    checkpoint: str | None = None,
) -> RunSnapshot:
    """Transition one branch without blocking independent runnable branches."""
    matches = [
        index for index, branch in enumerate(snapshot.branches) if branch.branch_id == branch_id
    ]
    if len(matches) != 1:
        raise InvalidRunTransition(f"unknown or duplicate branch: {branch_id}")
    index = matches[0]
    current = snapshot.branches[index]
    updates: dict[str, object] = {"status": target}
    if current.status in _BRANCH_PAUSED:
        if target is not current.resume_status or checkpoint != current.checkpoint:
            raise InvalidRunTransition("paused branch must resume from its checkpoint")
        updates["resume_status"] = None
        updates["checkpoint"] = current.checkpoint
    elif target in _BRANCH_PAUSED:
        if target not in _BRANCH_TRANSITIONS.get(current.status, set()) or checkpoint is None:
            raise InvalidRunTransition("branch pause requires active state and checkpoint")
        updates["resume_status"] = current.status
        updates["checkpoint"] = checkpoint
    elif target not in _BRANCH_TRANSITIONS.get(current.status, set()):
        raise InvalidRunTransition(f"illegal branch transition: {current.status} -> {target}")

    branches = list(snapshot.branches)
    branches[index] = BranchSnapshot.model_validate({**current.model_dump(), **updates})
    run_updates: dict[str, object] = {"branches": branches}
    runnable = {BranchStatus.PENDING, BranchStatus.RUNNING}
    if any(branch.status in runnable for branch in branches):
        if snapshot.run_status in _PAUSED:
            run_updates["run_status"] = snapshot.resume_status or RunStatus.RUNNING
            run_updates["resume_status"] = None
            run_updates["checkpoint"] = checkpoint
    elif any(branch.status in _BRANCH_PAUSED for branch in branches):
        run_updates["resume_status"] = (
            snapshot.resume_status if snapshot.run_status in _PAUSED else snapshot.run_status
        )
        run_updates["run_status"] = (
            RunStatus.AWAITING_ALIGNMENT
            if any(branch.status is BranchStatus.AWAITING_ALIGNMENT for branch in branches)
            else RunStatus.WAITING_DATA
        )
        run_updates["checkpoint"] = checkpoint
    return RunSnapshot.model_validate({**snapshot.model_dump(), **run_updates})
