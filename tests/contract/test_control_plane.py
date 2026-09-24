import json
from pathlib import Path

import pytest
import yaml

from harness.core.capability import resolve_capability
from harness.core.contracts.models import ErrorEnvelope, NoOp
from harness.core.memory import MemoryError, assemble
from harness.core.policy import Policy, PolicyError, compose_rules
from harness.core.registry import Registry, RegistryError

ROOT = Path(__file__).resolve().parents[2]


def test_monthly_manifest_and_echo_fixture_materialize() -> None:
    registry = Registry(ROOT)
    packs = registry.load_rule_packs("docs/30-constraints/rule-packs.yaml")
    profile = registry.load_profile("config/profile.yaml")
    assert profile["schema_version"] == 2

    monthly = registry.load_manifest(
        "docs/20-domain/playbooks/monthly-business-review/manifest.yaml"
    )
    materialized = registry.materialize(monthly, packs, ["shopify", "tiktok"])
    assert "orders" in materialized["core_capabilities"]
    assert "platform:shopify" in materialized["effective_rule_packs"]
    assert "platform:tiktok" in materialized["effective_rule_packs"]

    echo = registry.load_manifest("tests/fixtures/playbooks/echo.yaml")
    echo_plan = registry.materialize(echo, packs, ["shopify"])
    assert echo_plan["playbook_id"] == "echo"
    assert echo_plan["playbook_id"] != monthly["id"]


def test_registry_rejects_markdown_unknown_version_and_dangling_refs(tmp_path: Path) -> None:
    markdown = tmp_path / "playbook.md"
    markdown.write_text("# not a contract", encoding="utf-8")
    with pytest.raises(RegistryError, match="markdown"):
        Registry(tmp_path).load_manifest("playbook.md")

    (tmp_path / "bad.yaml").write_text("schema_version: 9\nid: x\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="schema_version"):
        Registry(tmp_path).load_manifest("bad.yaml")

    registry = Registry(ROOT)
    monthly = registry.load_manifest(
        "docs/20-domain/playbooks/monthly-business-review/manifest.yaml"
    )
    packs = registry.load_rule_packs("docs/30-constraints/rule-packs.yaml")
    with pytest.raises(RegistryError, match="target platforms"):
        registry.materialize(monthly, packs, [])
    with pytest.raises(RegistryError, match="dangling"):
        registry.materialize(monthly, packs, ["missing-platform"])


def test_registry_rejects_incomplete_and_duplicate_contracts(tmp_path: Path) -> None:
    echo = yaml.safe_load((ROOT / "tests/fixtures/playbooks/echo.yaml").read_text(encoding="utf-8"))
    (tmp_path / "echo.json").write_text(json.dumps(echo), encoding="utf-8")
    assert Registry(tmp_path).load_manifest("echo.json")["id"] == "echo"
    (tmp_path / "notes.markdown").write_text("# notes", encoding="utf-8")
    with pytest.raises(RegistryError, match="markdown"):
        Registry(tmp_path).load_manifest("notes.markdown")
    (tmp_path / "list.yaml").write_text("- 1\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="object"):
        Registry(tmp_path).load_manifest("list.yaml")
    (tmp_path / "partial.yaml").write_text("schema_version: 1\nid: echo\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="missing fields"):
        Registry(tmp_path).load_manifest("partial.yaml")
    echo["steps"].append(dict(echo["steps"][0]))
    (tmp_path / "dup.yaml").write_text(yaml.safe_dump(echo), encoding="utf-8")
    with pytest.raises(RegistryError, match="duplicate step"):
        Registry(tmp_path).load_manifest("dup.yaml")
    (tmp_path / "packs.yaml").write_text("schema_version: 9\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="rule-pack"):
        Registry(tmp_path).load_rule_packs("packs.yaml")
    (tmp_path / "empty.yaml").write_text("schema_version: 1\npacks: {}\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="non-empty"):
        Registry(tmp_path).load_rule_packs("empty.yaml")
    (tmp_path / "repeat.yaml").write_text(
        "schema_version: 1\npacks:\n  core:\n    rules: [R-1, R-1]\n",
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="duplicate rule"):
        Registry(tmp_path).load_rule_packs("repeat.yaml")
    (tmp_path / "profile.yaml").write_text("schema_version: nope\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="profile"):
        Registry(tmp_path).load_profile("profile.yaml")
    with pytest.raises(RegistryError, match="escapes"):
        Registry(tmp_path).load_manifest("../outside.yaml")
    echo["rule_packs"]["fixed"] = ["missing-pack"]
    with pytest.raises(RegistryError, match="dangling"):
        Registry(ROOT).materialize(echo, {"packs": {"core": {}}}, ["shopify"])


def test_policy_denies_network_by_default_and_blocks_same_scope_conflict() -> None:
    packs = Registry(ROOT).load_rule_packs("docs/30-constraints/rule-packs.yaml")["packs"]
    selected = ["core", "domain:ecommerce", "platform:shopify", "playbook:monthly-business-review"]
    composed = compose_rules(packs, selected)
    assert composed["R-01"] == "core"

    policy = Policy(allowlist=set())
    with pytest.raises(PolicyError, match="network denied"):
        policy.check({"capability": "llm", "network": True, "classification": "internal"})
    assert policy.check({"capability": "local", "network": False}) == "allow"

    conflict = {
        "left": {"scope": "platform", "rules": ["R-1"]},
        "right": {"scope": "platform", "rules": ["R-1"]},
    }
    with pytest.raises(PolicyError, match="same-scope"):
        compose_rules(conflict, ["left", "right"])


def test_memory_rejects_previous_metric_numbers(tmp_path: Path) -> None:
    errors = tmp_path / "errors" / "index.md"
    errors.parent.mkdir()
    errors.write_text("index", encoding="utf-8")
    bundle = assemble(caliber_paths=[tmp_path / "docs" / "metrics.md"], errors_index=errors)
    assert bundle["previous_metric_values"] == {}
    with pytest.raises(MemoryError, match="previous metric"):
        assemble(
            caliber_paths=[],
            errors_index=errors,
            previous_metrics={"M101": 10},
        )


@pytest.mark.parametrize(
    ("required", "enabled", "credentials", "expected"),
    [
        (False, False, True, NoOp),
        (True, False, True, ErrorEnvelope),
        (True, True, False, ErrorEnvelope),
        (True, True, True, type(None)),
    ],
)
def test_capability_noop_matrix(
    required: bool, enabled: bool, credentials: bool, expected: type
) -> None:
    capability = "db-read" if not credentials else "orders"
    result = resolve_capability(
        capability=capability,
        required=required,
        enabled=enabled,
        credentials_present=credentials,
    )
    assert isinstance(result, expected)
    if isinstance(result, ErrorEnvelope) and not credentials:
        assert result.code == "credentials-missing"
