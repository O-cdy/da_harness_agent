import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from harness.core.contracts.schema import (
    SchemaCompatibilityError,
    assert_schema_backward_compatible,
    contract_schema_bundle,
    write_contract_schema_bundle,
)

ROOT = Path(__file__).resolve().parents[2]


def test_generated_v1_bundle_matches_export_api() -> None:
    generated = json.loads((ROOT / "schemas/contracts-v1.json").read_text(encoding="utf-8"))

    assert generated == contract_schema_bundle()
    assert generated["schema_version"] == 1
    assert {
        "NoOp",
        "ErrorEnvelope",
        "ArtifactEnvelope",
        "TraceEvent",
        "Plan",
        "PlanStep",
        "ApprovalRecord",
        "BranchSnapshot",
        "RunSnapshot",
        "QualityAssertion",
        "SourceManifest",
    } <= generated["contracts"].keys()

    run_schema = generated["contracts"]["RunSnapshot"]
    pause_condition = run_schema["allOf"][0]
    assert set(pause_condition["then"]["required"]) >= {"checkpoint", "resume_status"}
    assert set(pause_condition["then"]["properties"]["resume_status"]["enum"]).isdisjoint(
        {"completed", "failed", "cancelled", "revision_required"}
    )


def test_schema_compatibility_rejects_removed_newly_required_and_narrowed_fields() -> None:
    published = {
        "schema_version": 1,
        "contracts": {
            "Example": {
                "type": "object",
                "properties": {
                    "stable": {"type": "string"},
                    "optional": {"type": ["string", "null"]},
                },
                "required": ["stable"],
            }
        },
    }

    removed = json.loads(json.dumps(published))
    del removed["contracts"]["Example"]["properties"]["stable"]
    with pytest.raises(SchemaCompatibilityError, match="removed"):
        assert_schema_backward_compatible(published, removed)

    newly_required = json.loads(json.dumps(published))
    newly_required["contracts"]["Example"]["required"].append("optional")
    with pytest.raises(SchemaCompatibilityError, match="required"):
        assert_schema_backward_compatible(published, newly_required)

    narrowed = json.loads(json.dumps(published))
    narrowed["contracts"]["Example"]["properties"]["optional"]["type"] = "string"
    with pytest.raises(SchemaCompatibilityError, match="type narrowed"):
        assert_schema_backward_compatible(published, narrowed)


def test_schema_compatibility_rejects_tightened_constraints() -> None:
    published = {
        "schema_version": 1,
        "contracts": {
            "Example": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "count": {"type": "integer"},
                    "tags": {"type": "array", "items": {"type": ["string", "null"]}},
                    "choice": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
                },
                "required": ["name"],
            }
        },
    }

    def narrowed(mutate: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        candidate = cast(dict[str, Any], json.loads(json.dumps(published)))
        example = cast(dict[str, Any], candidate["contracts"]["Example"])
        mutate(example)
        return candidate

    cases = [
        ("pattern", lambda node: node["properties"]["name"].__setitem__("pattern", "^[a-z]+$")),
        ("maxLength", lambda node: node["properties"]["name"].__setitem__("maxLength", 3)),
        ("minimum", lambda node: node["properties"]["count"].__setitem__("minimum", 1)),
        ("enum", lambda node: node["properties"]["name"].__setitem__("enum", ["a"])),
        ("const", lambda node: node["properties"]["name"].__setitem__("const", "a")),
        (
            "items",
            lambda node: node["properties"]["tags"]["items"].__setitem__("type", "string"),
        ),
        (
            "anyOf",
            lambda node: node["properties"]["choice"].__setitem__("anyOf", [{"type": "string"}]),
        ),
        ("allOf", lambda node: node.__setitem__("allOf", [{"required": ["count"]}])),
    ]
    for label, mutate in cases:
        with pytest.raises(SchemaCompatibilityError, match=label):
            assert_schema_backward_compatible(published, narrowed(mutate))


def test_schema_compatibility_rejects_remaining_constraint_shapes() -> None:
    published = {
        "schema_version": 1,
        "contracts": {
            "Example": {
                "type": "object",
                "properties": {
                    "ref": {"$ref": "#/$defs/Old"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "choice": {"oneOf": [{"type": "string"}, {"type": "integer"}]},
                    "prefix": {"prefixItems": [{"type": "string"}]},
                },
                "dependentSchemas": {"flag": {"required": ["ref"]}},
                "$defs": {"Old": {"type": "string"}, "Gone": {"type": "string"}},
            }
        },
    }

    def candidate(mutate: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        copied = cast(dict[str, Any], json.loads(json.dumps(published)))
        mutate(cast(dict[str, Any], copied["contracts"]["Example"]))
        return copied

    cases = [
        (
            "ref tightened",
            lambda node: node["properties"]["ref"].__setitem__("$ref", "#/$defs/New"),
        ),
        ("uniqueItems", lambda node: node["properties"]["tags"].__setitem__("uniqueItems", True)),
        (
            "additionalProperties",
            lambda node: node.__setitem__("additionalProperties", False),
        ),
        (
            "oneOf",
            lambda node: node["properties"]["choice"].__setitem__("oneOf", [{"type": "string"}]),
        ),
        (
            "prefixItems",
            lambda node: node["properties"]["prefix"].__setitem__(
                "prefixItems",
                [{"type": "string"}, {"type": "integer"}],
            ),
        ),
        ("not", lambda node: node.__setitem__("not", {"required": ["ref"]})),
        (
            "dependentSchemas",
            lambda node: node["dependentSchemas"].__setitem__("extra", {"required": ["tags"]}),
        ),
        ("definitions removed", lambda node: node["$defs"].__delitem__("Gone")),
    ]
    for label, mutate in cases:
        with pytest.raises(SchemaCompatibilityError, match=label):
            assert_schema_backward_compatible(published, candidate(mutate))

    changed_version = json.loads(json.dumps(published))
    changed_version["schema_version"] = 2
    with pytest.raises(SchemaCompatibilityError, match="version"):
        assert_schema_backward_compatible(published, changed_version)


def test_schema_export_checks_git_head_not_only_working_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "contracts-v1.json"
    candidate = contract_schema_bundle()
    path.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    published = json.loads(json.dumps(candidate))
    published["contracts"]["RunSnapshot"]["properties"]["run_id"] = {"type": "string"}

    monkeypatch.setattr(
        "harness.core.contracts.schema.git_published_bundle",
        lambda _: published,
    )
    with pytest.raises(SchemaCompatibilityError):
        write_contract_schema_bundle(path)
    assert json.loads(path.read_text(encoding="utf-8")) == candidate


def test_checked_in_bundle_is_compatible_with_git_head() -> None:
    from harness.core.contracts.schema import git_published_bundle

    path = ROOT / "schemas/contracts-v1.json"
    published = git_published_bundle(path)
    assert published is not None
    assert_schema_backward_compatible(published, contract_schema_bundle())


def test_schema_export_refuses_to_overwrite_incompatible_published_bundle(
    tmp_path: Path,
) -> None:
    path = tmp_path / "contracts-v1.json"
    published = contract_schema_bundle()
    published["contracts"]["PublishedOnly"] = {
        "type": "object",
        "properties": {"stable": {"type": "string"}},
        "required": ["stable"],
    }
    original = json.dumps(published, indent=2, sort_keys=True) + "\n"
    path.write_text(original, encoding="utf-8")

    with pytest.raises(SchemaCompatibilityError, match="contract removed"):
        write_contract_schema_bundle(path)

    assert path.read_text(encoding="utf-8") == original
