"""Playbook DAG runner. It loads manifests and does not import concrete implementations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness.core.contracts.models import DataCompleteness
from harness.core.contracts.redaction import redact
from harness.core.contracts.state import (
    BranchSnapshot,
    BranchStatus,
    ReportTier,
    RunSnapshot,
    RunStatus,
    transition_branch,
    transition_run,
)
from harness.core.memory import assemble
from harness.core.policy import Policy
from harness.core.registry import Registry

_PHASES = ("preflight", "plan", "sql", "snapshot")
_MAINLINE = (
    RunStatus.PLANNING,
    RunStatus.PLANNED,
    RunStatus.AWAITING_C1,
    RunStatus.PREPARING_SQL,
    RunStatus.AWAITING_C2,
    RunStatus.SNAPSHOTTING,
)
_RESUMABLE = frozenset(
    {
        RunStatus.PLANNING.value,
        RunStatus.PREPARING_SQL.value,
        RunStatus.SNAPSHOTTING.value,
        RunStatus.RUNNING.value,
        RunStatus.VALIDATING.value,
        RunStatus.RENDERING.value,
        RunStatus.SEALING.value,
        RunStatus.EVALUATING.value,
    }
)

SqlReview = Callable[[str], dict[str, Any]]
SqlExecute = Callable[[dict[str, Any]], dict[str, Any]]


class OrchestratorError(ValueError):
    """A playbook run violated order, checkpoint, or manifest rules."""


def fingerprint(payload: dict[str, Any]) -> str:
    """Hash a JSON payload. The prefix matches the contract fingerprint pattern."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def resume(checkpoint: str | None, resume_status: str) -> str:
    """Return to the checkpointed active state. A missing checkpoint cannot resume."""
    if checkpoint is None or not checkpoint.startswith("sha256:"):
        raise OrchestratorError("resume requires a committed checkpoint")
    if resume_status not in _RESUMABLE:
        raise OrchestratorError("resume status is not an active state")
    return resume_status


def run_playbook(
    root: Path,
    manifest_path: str,
    target_platforms: list[str],
    *,
    rule_pack_path: str = "docs/30-constraints/rule-packs.yaml",
    evidence_dir: Path | None = None,
    fail_closed: bool = False,
    statements: list[str] | None = None,
    review_sql: SqlReview | None = None,
    execute_sql: SqlExecute | None = None,
    c2_approved: bool = False,
    previous_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run preflight, plan, SQL review, and snapshot. Unapproved SQL is not executed."""
    partial: Path | None = None
    try:
        registry = Registry(root)
        manifest = registry.load_manifest(manifest_path)
        packs = registry.load_rule_packs(rule_pack_path)
        materialized = registry.materialize(manifest, packs, target_platforms)
        memory = assemble(
            caliber_paths=_caliber_paths(root),
            errors_index=root / "errors" / "index.md",
            previous_evidence=previous_evidence,
        )
        if evidence_dir is not None:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            partial = evidence_dir / "partial.tmp"
            partial.write_text("partial", encoding="utf-8")
        if fail_closed:
            raise OrchestratorError("run cancelled")
        snapshot = _start(manifest)
        for status in _MAINLINE:
            snapshot = transition_run(snapshot, status)
        sql_archive = _review_sql(
            statements or [],
            review_sql=review_sql,
            execute_sql=execute_sql,
            c2_approved=c2_approved,
        )
        snapshot = _run_branches(snapshot, manifest["steps"])
        approvals = _approvals(manifest["id"], target_platforms, sql_archive)
        result: dict[str, Any] = {
            "phase_order": list(_PHASES),
            "playbook_id": manifest["id"],
            "run_status": snapshot.run_status.value,
            "report_tier": snapshot.report_tier.value,
            "materialized": materialized,
            "memory": memory,
            "sql_archive": sql_archive,
            "approvals": approvals,
            "branches": _public_branches(snapshot),
            "approval_fingerprint": approvals["c1"]["fingerprint"],
        }
        if evidence_dir is not None:
            _write_evidence(evidence_dir, result)
            (evidence_dir / "partial.tmp").unlink(missing_ok=True)
        return result
    except Exception:
        _cleanup(partial)
        raise


def _caliber_paths(root: Path) -> list[Path]:
    candidates = (
        root / "docs" / "20-domain" / "metrics.md",
        root / "config" / "profile.yaml",
    )
    return [path for path in candidates if path.is_file()]


def _start(manifest: dict[str, Any]) -> RunSnapshot:
    branches = [
        BranchSnapshot(
            branch_id=str(step["step_id"]),
            step_id=str(step["step_id"]),
            status=BranchStatus.PENDING,
        )
        for step in manifest["steps"]
    ]
    return RunSnapshot(
        run_id="run-1",
        plan_revision=1,
        revision=0,
        run_status=RunStatus.CREATED,
        data_completeness=DataCompleteness.PARTIAL,
        report_tier=ReportTier.DRY_RUN,
        branches=branches,
    )


def _review_sql(
    statements: list[str],
    *,
    review_sql: SqlReview | None,
    execute_sql: SqlExecute | None,
    c2_approved: bool,
) -> list[dict[str, Any]]:
    if not statements:
        return [{"executed": False, "reason": "run has no statement"}]
    if review_sql is None:
        raise OrchestratorError("sql review is absent")
    reviewed = [review_sql(statement) for statement in statements]
    if not c2_approved:
        return [
            {"executed": False, "reason": "c2 placeholder is not approval", "sql": item.get("sql")}
            for item in reviewed
        ]
    if execute_sql is None:
        raise OrchestratorError("sql executor is absent")
    policy = Policy(allowlist={"db-read"})
    event = {
        "capability": "db-read",
        "network": False,
        "classification": "internal",
        "enforce_capability": True,
    }

    def _bind(statement: dict[str, Any]) -> Callable[[], dict[str, Any]]:
        def _execute() -> dict[str, Any]:
            return execute_sql(statement)

        return _execute

    return [policy.around(event, _bind(item)) for item in reviewed]


def _run_branches(snapshot: RunSnapshot, steps: list[dict[str, Any]]) -> RunSnapshot:
    for step in steps:
        step_id = str(step["step_id"])
        snapshot = transition_branch(snapshot, step_id, BranchStatus.RUNNING)
        if step.get("on_unsupported") == "await_alignment":
            checkpoint = step.get("checkpoint") or fingerprint(
                {"step_id": step_id, "state": "paused"}
            )
            if not isinstance(checkpoint, str) or not checkpoint.startswith("sha256:"):
                raise OrchestratorError("pause requires a committed checkpoint")
            snapshot = transition_branch(
                snapshot,
                step_id,
                BranchStatus.AWAITING_ALIGNMENT,
                checkpoint=checkpoint,
            )
            continue
        snapshot = transition_branch(
            snapshot,
            step_id,
            BranchStatus.COMPLETED,
            checkpoint=fingerprint({"step_id": step_id, "state": "completed"}),
        )
    return snapshot


def _approvals(
    playbook_id: str,
    platforms: list[str],
    sql_archive: list[dict[str, Any]],
) -> dict[str, dict[str, str]]:
    c1 = fingerprint({"scope": "c1", "playbook_id": playbook_id, "platforms": platforms})
    c2 = fingerprint({"scope": "c2", "sql": sql_archive})
    c3 = fingerprint({"scope": "c3", "status": "not_submitted"})
    return {
        "c1": {"fingerprint": c1, "status": "placeholder"},
        "c2": {"fingerprint": c2, "status": "placeholder"},
        "c3": {"fingerprint": c3, "status": "not_submitted"},
    }


def _public_branches(snapshot: RunSnapshot) -> list[dict[str, Any]]:
    published: list[dict[str, Any]] = []
    for branch in snapshot.branches:
        if branch.status is BranchStatus.AWAITING_ALIGNMENT:
            published.append(
                {
                    "step_id": branch.step_id,
                    "status": branch.status.value,
                    "checkpoint": branch.checkpoint,
                }
            )
            continue
        published.append(
            {
                "step_id": branch.step_id,
                "status": branch.status.value,
                "report_tier": ReportTier.DRY_RUN.value,
                "checkpoint": fingerprint({"step_id": branch.step_id, "state": "completed"}),
            }
        )
    return published


def _write_evidence(evidence_dir: Path, result: dict[str, Any]) -> None:
    safe = redact(result)
    (evidence_dir / "plan.md").write_text(_plan_markdown(result), encoding="utf-8")
    (evidence_dir / "trace.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in _trace_events(result)),
        encoding="utf-8",
    )
    (evidence_dir / "envelope.json").write_text(
        json.dumps(safe, sort_keys=True),
        encoding="utf-8",
    )
    (evidence_dir / "checkpoint.json").write_text(
        json.dumps({"branches": safe["branches"], "approvals": safe["approvals"]}, sort_keys=True),
        encoding="utf-8",
    )


def _trace_events(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Record state, policy, approval, and artifact summaries. SQL text stays out."""
    events = [
        _trace_event(index, "state", str(phase), str(phase))
        for index, phase in enumerate(result["phase_order"], start=1)
    ]
    archive = result["sql_archive"]
    reasons = sorted(
        {
            str(item.get("reason", "executed" if item.get("executed") else "reviewed"))
            for item in archive
        }
    )
    cursor = len(events) + 1
    events.append(_trace_event(cursor, "policy", "sql", ",".join(reasons) or "no statement"))
    events.append(
        _trace_event(cursor + 1, "approval", "c3", str(result["approvals"]["c3"]["status"]))
    )
    events.append(_trace_event(cursor + 2, "artifact", "evidence", "checkpoint"))
    return events


def _trace_event(index: int, event_type: str, step_id: str, summary: str) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "event_id": f"evt-{index}",
        "event_type": event_type,
        "run_id": "run-1",
        "plan_revision": 1,
        "step_id": step_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "input_refs": [],
        "result_summary": summary,
        "duration_ms": 0,
        "classification": "internal",
    }


def _plan_markdown(result: dict[str, Any]) -> str:
    lines = [f"# {result['playbook_id']}", "", "report_tier: dry_run", ""]
    for phase in result["phase_order"]:
        lines.append(f"- {phase}")
    lines.append("")
    return "\n".join(lines)


def _cleanup(partial: Path | None) -> None:
    if partial is not None and partial.exists():
        partial.unlink()
        parent = partial.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
