import pytest

from harness.core.contracts.models import DataCompleteness, ErrorEnvelope
from harness.core.contracts.state import (
    InvalidRunTransition,
    ReportTier,
    RunSnapshot,
    RunStatus,
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
    paused = transition_run(make_snapshot(RunStatus.RUNNING), pause_status)

    assert paused.resume_status is RunStatus.RUNNING
    assert transition_run(paused, RunStatus.RUNNING).resume_status is None
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


def test_paused_run_can_be_cancelled_or_failed() -> None:
    paused = transition_run(
        make_snapshot(RunStatus.RUNNING),
        RunStatus.AWAITING_ALIGNMENT,
    )
    cancelling = transition_run(paused, RunStatus.CANCEL_REQUESTED)
    assert cancelling.resume_status is None

    paused_again = transition_run(
        make_snapshot(RunStatus.RUNNING),
        RunStatus.WAITING_DATA,
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
    assert transition_run(paused_again, RunStatus.FAILED, error=error).error == error
