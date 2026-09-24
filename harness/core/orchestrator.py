"""Playbook DAG runner. It loads manifests and does not import concrete implementations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from harness.core.contracts.redaction import redact
from harness.core.registry import Registry

_PHASES = ("preflight", "plan", "sql", "snapshot")


class OrchestratorError(ValueError):
    """A playbook run violated order, checkpoint, or manifest rules."""


def fingerprint(payload: dict[str, Any]) -> str:
    """Hash a JSON payload. The prefix matches the contract fingerprint pattern."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def resume(checkpoint: str | None) -> str:
    """Return to the checkpointed active state. A missing checkpoint cannot resume."""
    if checkpoint is None or not checkpoint.startswith("sha256:"):
        raise OrchestratorError("resume requires a committed checkpoint")
    return "active"


def run_playbook(
    root: Path,
    manifest_path: str,
    target_platforms: list[str],
    *,
    rule_pack_path: str = "docs/30-constraints/rule-packs.yaml",
    evidence_dir: Path | None = None,
    fail_closed: bool = False,
) -> dict[str, Any]:
    """Run preflight, materialize the plan, then each independent branch."""
    partial: Path | None = None
    try:
        registry = Registry(root)
        manifest = registry.load_manifest(manifest_path)
        packs = registry.load_rule_packs(rule_pack_path)
        materialized = registry.materialize(manifest, packs, target_platforms)
        if evidence_dir is not None:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            partial = evidence_dir / "partial.tmp"
            partial.write_text("partial", encoding="utf-8")
        if fail_closed:
            raise OrchestratorError("run cancelled")
        branches = [_branch(step) for step in manifest["steps"]]
        approval = fingerprint(
            {
                "playbook_id": manifest["id"],
                "platforms": list(target_platforms),
                "phases": list(_PHASES),
                "branches": [branch["step_id"] for branch in branches],
            }
        )
        result: dict[str, Any] = {
            "phase_order": list(_PHASES),
            "playbook_id": manifest["id"],
            "materialized": materialized,
            "branches": branches,
            "approval_fingerprint": approval,
        }
        if evidence_dir is not None:
            _write_evidence(evidence_dir, result)
            (evidence_dir / "partial.tmp").unlink(missing_ok=True)
        return result
    except Exception:
        _cleanup(partial)
        raise


def _branch(step: dict[str, Any]) -> dict[str, Any]:
    step_id = str(step["step_id"])
    if step.get("on_unsupported") == "await_alignment":
        checkpoint = step.get("checkpoint") or fingerprint({"step_id": step_id, "state": "paused"})
        if not isinstance(checkpoint, str) or not checkpoint.startswith("sha256:"):
            raise OrchestratorError("pause requires a committed checkpoint")
        return {"step_id": step_id, "status": "awaiting_alignment", "checkpoint": checkpoint}
    return {
        "step_id": step_id,
        "status": "completed",
        "report_tier": "dry_run",
        "checkpoint": fingerprint({"step_id": step_id, "state": "completed"}),
    }


def _write_evidence(evidence_dir: Path, result: dict[str, Any]) -> None:
    safe = redact(result)
    (evidence_dir / "plan.md").write_text(_plan_markdown(result), encoding="utf-8")
    (evidence_dir / "trace.json").write_text(
        json.dumps({"phases": result["phase_order"]}, sort_keys=True),
        encoding="utf-8",
    )
    (evidence_dir / "envelope.json").write_text(
        json.dumps(safe, sort_keys=True),
        encoding="utf-8",
    )
    (evidence_dir / "checkpoint.json").write_text(
        json.dumps({"branches": safe["branches"]}, sort_keys=True),
        encoding="utf-8",
    )


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
