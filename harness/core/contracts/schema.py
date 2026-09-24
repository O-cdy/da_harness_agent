"""Machine-readable JSON Schema export for the stable v1 contracts."""

from __future__ import annotations

from typing import Any

from .models import (
    ApprovalRecord,
    ArtifactEnvelope,
    ErrorEnvelope,
    IdempotencyKey,
    NoOp,
    Plan,
    PlanStep,
    QualityAssertion,
    SourceManifest,
    SourceManifestEntry,
    StrictContract,
    TraceEvent,
)
from .state import BranchSnapshot, RunSnapshot

_CONTRACTS: tuple[type[StrictContract], ...] = (
    NoOp,
    ErrorEnvelope,
    ArtifactEnvelope,
    IdempotencyKey,
    TraceEvent,
    PlanStep,
    Plan,
    ApprovalRecord,
    BranchSnapshot,
    RunSnapshot,
    QualityAssertion,
    SourceManifestEntry,
    SourceManifest,
)


def contract_schema_bundle() -> dict[str, Any]:
    """Return the canonical, deterministic v1 schema bundle."""
    return {
        "schema_version": 1,
        "contracts": {model.__name__: model.model_json_schema() for model in _CONTRACTS},
    }
