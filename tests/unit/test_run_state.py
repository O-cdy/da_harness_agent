import pytest

from harness.core.contracts.models import DataCompleteness, ErrorEnvelope
from harness.core.contracts.state import (
    BranchSnapshot,
    BranchStatus,
    InvalidRunTransition,
    ReportTier,
    RunSnapshot,
    RunStatus,
    transition_branch,
    transition_run,
)


def make_snapshot(status: RunStatus = RunStatus.CREATED) -> RunSnapshot:
    error = (
        ErrorEnvelope(
            code="E_TEST",
            category="test",
            severity="error",
            retryable=False,
            module_id="test",
            run_id="run-1",
            plan_revision=1,
            safe_message="safe",
        )
        if status is RunStatus.FAILED
        else None
    )
    return RunSnapshot(
        run_id="run-1",
        plan_revision=1,
        revision=0,
        run_status=status,
        data_completeness=DataCompleteness.PARTIAL,
        report_tier=ReportTier.DRY_RUN,
        error=error,
    )


def test_complete_mainline_is_accepted() -> None:
    statuses = [
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
    ]
    snapshot = make_snapshot()

    for status in statuses:
        snapshot = transition_run(snapshot, status)

    assert snapshot.run_status is RunStatus.COMPLETED


def test_illegal_transition_is_rejected() -> None:
    with pytest.raises(InvalidRunTransition, match=r"created.*running"):
        transition_run(make_snapshot(), RunStatus.RUNNING)


def test_cancel_and_revision_paths_are_explicit() -> None:
    cancelling = transition_run(make_snapshot(RunStatus.RUNNING), RunStatus.CANCEL_REQUESTED)
    assert transition_run(cancelling, RunStatus.CANCELLED).run_status is RunStatus.CANCELLED

    rejected = transition_run(make_snapshot(RunStatus.AWAITING_C3), RunStatus.REVISION_REQUIRED)
    replanning = transition_run(rejected, RunStatus.PLANNING)
    assert replanning.plan_revision == 2


@pytest.mark.parametrize("pause_status", [RunStatus.AWAITING_ALIGNMENT, RunStatus.WAITING_DATA])
def test_pause_branches_resume_only_the_interrupted_state(pause_status: RunStatus) -> None:
    paused = transition_run(
        make_snapshot(RunStatus.RUNNING),
        pause_status,
        checkpoint="checkpoint:run",
    )

    assert paused.resume_status is RunStatus.RUNNING
    assert (
        transition_run(
            paused,
            RunStatus.RUNNING,
            checkpoint="checkpoint:run",
        ).resume_status
        is None
    )
    with pytest.raises(InvalidRunTransition):
        transition_run(paused, RunStatus.VALIDATING)


def test_terminal_states_have_no_outgoing_transition() -> None:
    for status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
        with pytest.raises(InvalidRunTransition):
            transition_run(make_snapshot(status), RunStatus.PLANNING)


def test_failed_transition_requires_and_preserves_safe_error() -> None:
    with pytest.raises(InvalidRunTransition, match="requires ErrorEnvelope"):
        transition_run(make_snapshot(RunStatus.RUNNING), RunStatus.FAILED)

    error = ErrorEnvelope(
        code="E_RUNTIME",
        category="runtime",
        severity="error",
        retryable=False,
        module_id="executor",
        run_id="run-1",
        plan_revision=1,
        safe_message="safe",
    )
    failed = transition_run(make_snapshot(RunStatus.RUNNING), RunStatus.FAILED, error=error)
    assert failed.error == error


def test_paused_run_can_be_cancel_requested_but_not_jump_failed() -> None:
    paused = transition_run(
        make_snapshot(RunStatus.RUNNING),
        RunStatus.AWAITING_ALIGNMENT,
        checkpoint="checkpoint:alignment",
    )
    cancelling = transition_run(paused, RunStatus.CANCEL_REQUESTED)
    assert cancelling.resume_status is None

    paused_again = transition_run(
        make_snapshot(RunStatus.RUNNING),
        RunStatus.WAITING_DATA,
        checkpoint="checkpoint:data",
    )
    error = ErrorEnvelope(
        code="E_DATA",
        category="data",
        severity="error",
        retryable=True,
        module_id="ingest",
        run_id="run-1",
        plan_revision=1,
        safe_message="safe",
    )
    with pytest.raises(InvalidRunTransition):
        transition_run(paused_again, RunStatus.FAILED, error=error)


def test_one_branch_can_pause_while_an_independent_branch_keeps_run_active() -> None:
    run = make_snapshot(RunStatus.RUNNING).model_copy(
        update={
            "branches": [
                BranchSnapshot(
                    branch_id="platform-a",
                    step_id="extract-a",
                    status=BranchStatus.RUNNING,
                ),
                BranchSnapshot(
                    branch_id="platform-b",
                    step_id="extract-b",
                    status=BranchStatus.RUNNING,
                ),
            ]
        }
    )

    updated = transition_branch(
        run,
        "platform-a",
        BranchStatus.AWAITING_ALIGNMENT,
        checkpoint="checkpoint:a",
    )

    paused, independent = updated.branches
    assert updated.run_status is RunStatus.RUNNING
    assert paused.resume_status is BranchStatus.RUNNING
    assert paused.checkpoint == "checkpoint:a"
    assert independent.status is BranchStatus.RUNNING


def test_paused_branch_resumes_only_from_its_checkpoint() -> None:
    run = make_snapshot(RunStatus.RUNNING).model_copy(
        update={
            "branches": [
                BranchSnapshot(
                    branch_id="platform-a",
                    step_id="extract-a",
                    status=BranchStatus.RUNNING,
                )
            ]
        }
    )
    paused = transition_branch(
        run,
        "platform-a",
        BranchStatus.WAITING_DATA,
        checkpoint="checkpoint:a",
    )
    assert paused.run_status is RunStatus.WAITING_DATA
    assert paused.resume_status is RunStatus.RUNNING

    with pytest.raises(InvalidRunTransition):
        transition_branch(paused, "platform-a", BranchStatus.COMPLETED)

    resumed = transition_branch(
        paused,
        "platform-a",
        BranchStatus.RUNNING,
        checkpoint="checkpoint:a",
    )
    assert resumed.branches[0].resume_status is None
    assert resumed.branches[0].checkpoint == "checkpoint:a"
    assert resumed.run_status is RunStatus.RUNNING
    assert resumed.resume_status is None


def test_run_axes_and_error_identity_are_consistent() -> None:
    with pytest.raises(ValueError, match="formal_final"):
        make_snapshot().model_copy(
            update={"report_tier": ReportTier.FORMAL_FINAL}
        ).__class__.model_validate(
            {
                **make_snapshot().model_dump(),
                "report_tier": ReportTier.FORMAL_FINAL,
            }
        )

    error = ErrorEnvelope(
        code="E_RUNTIME",
        category="runtime",
        severity="error",
        retryable=False,
        module_id="executor",
        run_id="other-run",
        plan_revision=1,
        safe_message="safe",
    )
    with pytest.raises(ValueError, match="run_id"):
        RunSnapshot(
            run_id="run-1",
            plan_revision=1,
            revision=0,
            run_status=RunStatus.FAILED,
            data_completeness=DataCompleteness.PARTIAL,
            report_tier=ReportTier.DRY_RUN,
            error=error,
        )

    with pytest.raises(ValueError, match="plan_revision"):
        RunSnapshot(
            run_id="other-run",
            plan_revision=2,
            revision=0,
            run_status=RunStatus.FAILED,
            data_completeness=DataCompleteness.PARTIAL,
            report_tier=ReportTier.DRY_RUN,
            error=error,
        )

    with pytest.raises(ValueError, match="only failed"):
        make_snapshot(RunStatus.RUNNING).__class__(
            **{
                **make_snapshot(RunStatus.RUNNING).model_dump(),
                "error": error.model_copy(update={"run_id": "run-1"}),
            }
        )


def test_branch_pause_requires_checkpoint_and_branch_ids_are_unique() -> None:
    with pytest.raises(ValueError, match="checkpoint"):
        BranchSnapshot(
            branch_id="branch-1",
            step_id="step-1",
            status=BranchStatus.WAITING_DATA,
            resume_status=BranchStatus.RUNNING,
        )

    branch = BranchSnapshot(
        branch_id="branch-1",
        step_id="step-1",
        status=BranchStatus.RUNNING,
    )
    with pytest.raises(ValueError, match="duplicate branch_id"):
        RunSnapshot(
            run_id="run-1",
            plan_revision=1,
            revision=0,
            run_status=RunStatus.RUNNING,
            data_completeness=DataCompleteness.PARTIAL,
            report_tier=ReportTier.DRY_RUN,
            branches=[branch, branch],
        )


def test_branch_and_run_pause_shapes_reject_inconsistent_snapshots() -> None:
    with pytest.raises(ValueError, match="active resume_status"):
        BranchSnapshot(
            branch_id="branch-1",
            step_id="step-1",
            status=BranchStatus.WAITING_DATA,
            checkpoint="checkpoint:1",
            resume_status=BranchStatus.COMPLETED,
        )
    with pytest.raises(ValueError, match="cannot carry resume_status"):
        BranchSnapshot(
            branch_id="branch-1",
            step_id="step-1",
            status=BranchStatus.RUNNING,
            resume_status=BranchStatus.PENDING,
        )
    with pytest.raises(ValueError, match="resume_status"):
        RunSnapshot(
            run_id="run-1",
            plan_revision=1,
            revision=0,
            run_status=RunStatus.WAITING_DATA,
            data_completeness=DataCompleteness.PARTIAL,
            report_tier=ReportTier.DRY_RUN,
        )
    with pytest.raises(ValueError, match="requires ErrorEnvelope"):
        RunSnapshot(
            run_id="run-1",
            plan_revision=1,
            revision=0,
            run_status=RunStatus.FAILED,
            data_completeness=DataCompleteness.PARTIAL,
            report_tier=ReportTier.DRY_RUN,
        )
    runnable = BranchSnapshot(
        branch_id="branch-1",
        step_id="step-1",
        status=BranchStatus.RUNNING,
    )
    with pytest.raises(ValueError, match="runnable branch"):
        RunSnapshot(
            run_id="run-1",
            plan_revision=1,
            revision=0,
            run_status=RunStatus.WAITING_DATA,
            data_completeness=DataCompleteness.PARTIAL,
            report_tier=ReportTier.DRY_RUN,
            resume_status=RunStatus.RUNNING,
            checkpoint="checkpoint:run",
            branches=[runnable],
        )


def test_branch_transition_rejects_unknown_missing_checkpoint_and_illegal_target() -> None:
    run = make_snapshot(RunStatus.RUNNING).model_copy(
        update={
            "branches": [
                BranchSnapshot(
                    branch_id="branch-1",
                    step_id="step-1",
                    status=BranchStatus.PENDING,
                )
            ]
        }
    )
    with pytest.raises(InvalidRunTransition, match="unknown"):
        transition_branch(run, "missing", BranchStatus.RUNNING)
    with pytest.raises(InvalidRunTransition, match="checkpoint"):
        transition_branch(run, "branch-1", BranchStatus.WAITING_DATA)
    with pytest.raises(InvalidRunTransition, match="illegal branch"):
        transition_branch(run, "branch-1", BranchStatus.COMPLETED)


@pytest.mark.parametrize(
    "resume_status",
    [
        RunStatus.CREATED,
        RunStatus.PLANNED,
        RunStatus.AWAITING_C1,
        RunStatus.AWAITING_C2,
        RunStatus.AWAITING_C3,
        RunStatus.CANCEL_REQUESTED,
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.REVISION_REQUIRED,
    ],
)
def test_run_pause_rejects_terminal_or_revision_resume_status(
    resume_status: RunStatus,
) -> None:
    with pytest.raises(ValueError, match="active resume_status"):
        RunSnapshot(
            run_id="run-1",
            plan_revision=1,
            revision=0,
            run_status=RunStatus.WAITING_DATA,
            data_completeness=DataCompleteness.PARTIAL,
            report_tier=ReportTier.DRY_RUN,
            checkpoint="checkpoint:run",
            resume_status=resume_status,
        )


def test_run_pause_requires_committed_checkpoint() -> None:
    with pytest.raises(ValueError, match="checkpoint"):
        RunSnapshot(
            run_id="run-1",
            plan_revision=1,
            revision=0,
            run_status=RunStatus.AWAITING_ALIGNMENT,
            data_completeness=DataCompleteness.PARTIAL,
            report_tier=ReportTier.DRY_RUN,
            resume_status=RunStatus.RUNNING,
        )

    with pytest.raises(InvalidRunTransition, match="checkpoint"):
        transition_run(make_snapshot(RunStatus.RUNNING), RunStatus.WAITING_DATA)


def test_run_resume_requires_exact_checkpoint_and_cannot_jump_terminal() -> None:
    paused = transition_run(
        make_snapshot(RunStatus.RUNNING),
        RunStatus.WAITING_DATA,
        checkpoint="checkpoint:run",
    )

    with pytest.raises(InvalidRunTransition, match="checkpoint"):
        transition_run(paused, RunStatus.RUNNING)
    with pytest.raises(InvalidRunTransition, match="checkpoint"):
        transition_run(paused, RunStatus.RUNNING, checkpoint="checkpoint:other")
    for forbidden in (
        RunStatus.COMPLETED,
        RunStatus.CANCELLED,
        RunStatus.REVISION_REQUIRED,
    ):
        with pytest.raises(InvalidRunTransition):
            transition_run(paused, forbidden, checkpoint="checkpoint:run")

    error = ErrorEnvelope(
        code="E_RUNTIME",
        category="runtime",
        severity="error",
        retryable=False,
        module_id="executor",
        run_id="run-1",
        plan_revision=1,
        safe_message="safe",
    )
    with pytest.raises(InvalidRunTransition):
        transition_run(
            paused,
            RunStatus.FAILED,
            checkpoint="checkpoint:run",
            error=error,
        )

    resumed = transition_run(
        paused,
        RunStatus.RUNNING,
        checkpoint="checkpoint:run",
    )
    assert resumed.run_status is RunStatus.RUNNING
    assert resumed.resume_status is None
    assert resumed.checkpoint == "checkpoint:run"
