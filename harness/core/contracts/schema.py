"""Machine-readable JSON Schema export for the stable v1 contracts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

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


class SchemaCompatibilityError(ValueError):
    """A candidate schema would break an already published v1 consumer."""


def contract_schema_bundle() -> dict[str, Any]:
    """Return the canonical, deterministic v1 schema bundle."""
    return {
        "schema_version": 1,
        "contracts": {model.__name__: model.model_json_schema() for model in _CONTRACTS},
    }


def _schema_types(schema: dict[str, Any]) -> set[str] | None:
    declared = schema.get("type")
    if isinstance(declared, str):
        return {declared}
    if isinstance(declared, list) and all(isinstance(item, str) for item in declared):
        return set(declared)
    alternatives = schema.get("anyOf")
    if isinstance(alternatives, list):
        types: set[str] = set()
        for alternative in alternatives:
            if not isinstance(alternative, dict):
                return None
            alternative_types = _schema_types(alternative)
            if alternative_types is None:
                return None
            types.update(alternative_types)
        return types
    return None


def _check_schema_node(
    published: dict[str, Any],
    candidate: dict[str, Any],
    path: str,
) -> None:
    old_types = _schema_types(published)
    new_types = _schema_types(candidate)
    if old_types is not None and new_types is not None and not old_types <= new_types:
        raise SchemaCompatibilityError(f"{path}: type narrowed from {old_types} to {new_types}")

    old_required = set(published.get("required", []))
    new_required = set(candidate.get("required", []))
    added_required = new_required - old_required
    if added_required:
        raise SchemaCompatibilityError(f"{path}: newly required fields {sorted(added_required)}")

    old_properties = published.get("properties", {})
    new_properties = candidate.get("properties", {})
    if isinstance(old_properties, dict) and isinstance(new_properties, dict):
        removed = set(old_properties) - set(new_properties)
        if removed:
            raise SchemaCompatibilityError(f"{path}: fields removed {sorted(removed)}")
        for name, old_property in old_properties.items():
            new_property = new_properties[name]
            if isinstance(old_property, dict) and isinstance(new_property, dict):
                _check_schema_node(old_property, new_property, f"{path}.properties.{name}")

    old_defs = published.get("$defs", {})
    new_defs = candidate.get("$defs", {})
    if isinstance(old_defs, dict) and isinstance(new_defs, dict):
        removed_defs = set(old_defs) - set(new_defs)
        if removed_defs:
            raise SchemaCompatibilityError(f"{path}: definitions removed {sorted(removed_defs)}")
        for name, old_definition in old_defs.items():
            new_definition = new_defs[name]
            if isinstance(old_definition, dict) and isinstance(new_definition, dict):
                _check_schema_node(old_definition, new_definition, f"{path}.$defs.{name}")


def assert_schema_backward_compatible(
    published: dict[str, Any],
    candidate: dict[str, Any],
) -> None:
    """Reject destructive changes to a published schema bundle."""
    if published.get("schema_version") != candidate.get("schema_version"):
        raise SchemaCompatibilityError("schema bundle version changed")
    old_contracts = published.get("contracts")
    new_contracts = candidate.get("contracts")
    if not isinstance(old_contracts, dict) or not isinstance(new_contracts, dict):
        raise SchemaCompatibilityError("schema bundle contracts must be objects")
    removed_contracts = set(old_contracts) - set(new_contracts)
    if removed_contracts:
        raise SchemaCompatibilityError(f"contract removed: {sorted(removed_contracts)}")
    for name, old_contract in old_contracts.items():
        new_contract = new_contracts[name]
        if not isinstance(old_contract, dict) or not isinstance(new_contract, dict):
            raise SchemaCompatibilityError(f"contract {name} must be an object")
        _check_schema_node(old_contract, new_contract, f"contracts.{name}")


def write_contract_schema_bundle(path: Path) -> None:
    """Atomically write v1 only after checking the existing published bundle."""
    candidate = contract_schema_bundle()
    if path.exists():
        published = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(published, dict):
            raise SchemaCompatibilityError("published schema bundle must be an object")
        assert_schema_backward_compatible(published, candidate)
    payload = (json.dumps(candidate, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()
