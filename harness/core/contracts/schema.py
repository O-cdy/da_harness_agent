"""Machine-readable JSON Schema export for the stable v1 contracts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
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


_MIN_CONSTRAINTS = ("minLength", "minItems", "minProperties", "minimum", "exclusiveMinimum")
_MAX_CONSTRAINTS = ("maxLength", "maxItems", "maxProperties", "maximum", "exclusiveMaximum")
_EXACT_CONSTRAINTS = (
    "pattern",
    "format",
    "const",
    "multipleOf",
    "contentMediaType",
    "contentEncoding",
)
_SCHEMA_LISTS = ("allOf", "anyOf", "oneOf", "prefixItems")
_SCHEMA_OBJECTS = (
    "items",
    "additionalItems",
    "contains",
    "additionalProperties",
    "unevaluatedItems",
    "unevaluatedProperties",
    "propertyNames",
    "if",
    "then",
    "else",
    "not",
)


def _number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value


def _reject_tightened_constraints(
    published: dict[str, Any],
    candidate: dict[str, Any],
    path: str,
) -> None:
    if "$ref" in candidate and candidate.get("$ref") != published.get("$ref"):
        raise SchemaCompatibilityError(f"{path}: $ref tightened")
    for key in _EXACT_CONSTRAINTS:
        if key in candidate and published.get(key) != candidate[key]:
            raise SchemaCompatibilityError(f"{path}: {key} tightened")
    for key in _MIN_CONSTRAINTS:
        new_value = _number(candidate.get(key))
        old_value = _number(published.get(key)) if key in published else None
        if new_value is not None and (old_value is None or new_value > old_value):
            raise SchemaCompatibilityError(f"{path}: {key} tightened")
    for key in _MAX_CONSTRAINTS:
        new_value = _number(candidate.get(key))
        old_value = _number(published.get(key)) if key in published else None
        if new_value is not None and (old_value is None or new_value < old_value):
            raise SchemaCompatibilityError(f"{path}: {key} tightened")
    if candidate.get("uniqueItems") is True and published.get("uniqueItems") is not True:
        raise SchemaCompatibilityError(f"{path}: uniqueItems tightened")
    for keyword in ("anyOf", "oneOf"):
        old_union = published.get(keyword)
        new_union = candidate.get(keyword)
        if isinstance(new_union, list) and (
            not isinstance(old_union, list) or len(new_union) < len(old_union)
        ):
            raise SchemaCompatibilityError(f"{path}: {keyword} tightened")
    if "enum" in candidate:
        old_enum = published.get("enum")
        new_enum = candidate["enum"]
        if (
            not isinstance(old_enum, list)
            or not isinstance(new_enum, list)
            or any(item not in new_enum for item in old_enum)
        ):
            raise SchemaCompatibilityError(f"{path}: enum tightened")
    old_additional = published.get("additionalProperties", True)
    new_additional = candidate.get("additionalProperties", old_additional)
    if new_additional is False and old_additional is not False:
        raise SchemaCompatibilityError(f"{path}: additionalProperties tightened")


def _check_schema_node(
    published: dict[str, Any],
    candidate: dict[str, Any],
    path: str,
) -> None:
    _reject_tightened_constraints(published, candidate, path)
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

    for keyword in _SCHEMA_LISTS:
        old_items = published.get(keyword)
        new_items = candidate.get(keyword)
        if not isinstance(new_items, list):
            continue
        if not isinstance(old_items, list):
            raise SchemaCompatibilityError(f"{path}: {keyword} tightened")
        longer_is_tighter = keyword in {"allOf", "prefixItems"}
        if longer_is_tighter and len(new_items) > len(old_items):
            raise SchemaCompatibilityError(f"{path}: {keyword} tightened")
        compared = new_items if longer_is_tighter else old_items
        for index, _item in enumerate(compared):
            old_item = old_items[index]
            new_item = new_items[index]
            if isinstance(old_item, dict) and isinstance(new_item, dict):
                _check_schema_node(old_item, new_item, f"{path}.{keyword}[{index}]")

    for keyword in _SCHEMA_OBJECTS:
        old_child = published.get(keyword)
        new_child = candidate.get(keyword)
        if isinstance(old_child, dict) and isinstance(new_child, dict):
            _check_schema_node(old_child, new_child, f"{path}.{keyword}")
        elif (
            keyword == "not" and "not" in candidate and published.get("not") != candidate.get("not")
        ):
            raise SchemaCompatibilityError(f"{path}: not tightened")

    for keyword in ("patternProperties", "dependentSchemas"):
        old_map = published.get(keyword, {})
        new_map = candidate.get(keyword, {})
        if not isinstance(old_map, dict) or not isinstance(new_map, dict):
            continue
        for name, old_child in old_map.items():
            new_child = new_map.get(name)
            if isinstance(old_child, dict) and isinstance(new_child, dict):
                _check_schema_node(old_child, new_child, f"{path}.{keyword}.{name}")
            elif name not in new_map:
                continue
        added = set(new_map) - set(old_map)
        if added and keyword == "dependentSchemas":
            raise SchemaCompatibilityError(f"{path}: {keyword} tightened")


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


PUBLISHED_SCHEMA_REF = "origin/master"


def git_published_bundle(path: Path, ref: str = PUBLISHED_SCHEMA_REF) -> dict[str, Any] | None:
    """Return the schema bundle published at origin/master, when this path is tracked."""
    git = shutil.which("git")
    if git is None:
        return None
    try:
        repository = subprocess.run(  # noqa: S603
            [git, "rev-parse", "--show-toplevel"],
            cwd=path.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        if repository.returncode != 0:
            return None
        root = Path(repository.stdout.strip())
        relative = path.resolve().relative_to(root.resolve()).as_posix()
        if any(part in {"", ".", ".."} for part in relative.split("/")):
            return None
        if not ref or ref.startswith("-") or ":" in ref:
            return None
        show = subprocess.run(  # noqa: S603
            [git, "show", f"{ref}:{relative}"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if show.returncode != 0:
            return None
        payload = json.loads(show.stdout)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def write_contract_schema_bundle(path: Path) -> None:
    """Atomically write v1 only after checking the bundle published on origin/master."""
    candidate = contract_schema_bundle()
    published = git_published_bundle(path)
    if published is None and path.exists():
        published = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(published, dict):
            raise SchemaCompatibilityError("published schema bundle must be an object")
    if published is not None:
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
