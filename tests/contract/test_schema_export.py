import json
import os
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


def test_published_schema_baseline_reads_origin_master(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from harness.core.contracts.schema import PUBLISHED_SCHEMA_REF, git_published_bundle

    calls: list[list[str]] = []

    class _Result:
        def __init__(self, stdout: str) -> None:
            self.returncode = 0
            self.stdout = stdout

    def fake_run(args: list[str], **_kwargs: object) -> _Result:
        calls.append(list(args))
        if "rev-parse" in args:
            return _Result(str(ROOT))
        return _Result(json.dumps(contract_schema_bundle()))

    monkeypatch.setattr("harness.core.contracts.schema.shutil.which", lambda _name: "git")
    monkeypatch.setattr("harness.core.contracts.schema.subprocess.run", fake_run)
    loaded = git_published_bundle(ROOT / "schemas/contracts-v1.json")

    assert loaded == contract_schema_bundle()
    assert PUBLISHED_SCHEMA_REF == "origin/master"
    assert any(
        arg.startswith("origin/master:schemas/contracts-v1.json") for call in calls for arg in call
    )


def test_missing_origin_master_bundle_allows_initial_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from harness.core.contracts.schema import git_published_bundle

    class _Result:
        returncode = 1
        stdout = ""

    monkeypatch.setattr("harness.core.contracts.schema.shutil.which", lambda _name: "git")
    monkeypatch.setattr(
        "harness.core.contracts.schema.subprocess.run",
        lambda *_args, **_kwargs: _Result(),
    )
    assert git_published_bundle(ROOT / "schemas/contracts-v1.json") is None


def test_schema_compatibility_covers_malformed_nodes() -> None:
    published = {
        "schema_version": 1,
        "contracts": {
            "Example": {
                "type": "object",
                "properties": {
                    "name": "string",
                    "ok": {"type": "string"},
                    "loose": {"anyOf": ["nope"]},
                },
                "$defs": {"Old": "string", "Kept": {"type": "string"}},
                "allOf": ["text"],
                "anyOf": ["nope"],
                "patternProperties": {"^a": {"type": "string"}},
            }
        },
    }
    candidate = json.loads(json.dumps(published))
    candidate["contracts"]["Example"]["patternProperties"] = {}
    assert_schema_backward_compatible(published, candidate)
    bare = {
        "schema_version": 1,
        "contracts": {"Example": {"properties": [], "$defs": []}},
    }
    assert_schema_backward_compatible(bare, json.loads(json.dumps(bare)))

    broken = {"schema_version": 1, "contracts": []}
    with pytest.raises(SchemaCompatibilityError, match="object"):
        assert_schema_backward_compatible(published, broken)
    with pytest.raises(SchemaCompatibilityError, match="object"):
        assert_schema_backward_compatible(
            published,
            {"schema_version": 1, "contracts": {"Example": "nope"}},
        )


def test_schema_export_writes_initial_bundle_and_rejects_bad_baselines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from harness.core.contracts.schema import git_published_bundle

    monkeypatch.setattr("harness.core.contracts.schema.shutil.which", lambda _name: None)
    destination = tmp_path / "nested" / "contracts-v1.json"
    write_contract_schema_bundle(destination)
    assert json.loads(destination.read_text(encoding="utf-8")) == contract_schema_bundle()

    destination.write_text("[]\n", encoding="utf-8")
    with pytest.raises(SchemaCompatibilityError, match="object"):
        write_contract_schema_bundle(destination)

    class _Result:
        def __init__(self, code: int, stdout: str) -> None:
            self.returncode = code
            self.stdout = stdout

    def fake_run(args: list[str], **_kwargs: object) -> _Result:
        if "rev-parse" in args:
            return _Result(0, str(ROOT))
        if args[-1].startswith("-"):
            return _Result(1, "")
        return _Result(0, "[]")

    monkeypatch.setattr("harness.core.contracts.schema.shutil.which", lambda _name: "git")
    monkeypatch.setattr("harness.core.contracts.schema.subprocess.run", fake_run)
    assert git_published_bundle(ROOT / "schemas/contracts-v1.json", ref="-bad") is None
    assert git_published_bundle(ROOT / "schemas/contracts-v1.json") is None

    def invalid_json(args: list[str], **_kwargs: object) -> _Result:
        if "rev-parse" in args:
            return _Result(0, str(ROOT))
        return _Result(0, "not-json")

    monkeypatch.setattr("harness.core.contracts.schema.subprocess.run", invalid_json)
    assert git_published_bundle(ROOT / "schemas/contracts-v1.json") is None

    def missing_show(args: list[str], **_kwargs: object) -> _Result:
        if "rev-parse" in args:
            return _Result(0, str(ROOT))
        return _Result(1, "")

    monkeypatch.setattr("harness.core.contracts.schema.subprocess.run", missing_show)
    assert git_published_bundle(ROOT / "schemas/contracts-v1.json") is None

    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(os, "open", lambda *_args, **_kwargs: 7)
    monkeypatch.setattr(os, "close", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(os, "fsync", lambda _fd: None)
    monkeypatch.setattr("harness.core.contracts.schema.shutil.which", lambda _name: None)
    posix_destination = tmp_path / "posix" / "contracts-v1.json"
    write_contract_schema_bundle(posix_destination)
    assert posix_destination.is_file()


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
