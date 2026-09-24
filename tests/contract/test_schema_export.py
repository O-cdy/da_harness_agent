import json
from pathlib import Path

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
