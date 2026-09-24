import json
from pathlib import Path

from harness.core.contracts.schema import contract_schema_bundle

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
        "RunSnapshot",
        "SourceManifest",
    } <= generated["contracts"].keys()
