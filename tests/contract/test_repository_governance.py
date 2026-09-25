import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_ci_actions_are_pinned_to_commit_hashes() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    action_refs = re.findall(r"uses:\s+[^@\s]+@([^\s]+)", workflow)

    assert action_refs
    assert all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs)


def test_security_rules_are_in_core_rule_pack() -> None:
    rules = (ROOT / "docs/30-constraints/rules.md").read_text(encoding="utf-8")
    packs = yaml.safe_load(
        (ROOT / "docs/30-constraints/rule-packs.yaml").read_text(encoding="utf-8")
    )

    for rule_id in ("R-103", "R-104", "R-105"):
        assert f"| {rule_id} |" in rules
        assert rule_id in packs["packs"]["core"]["rules"]


def test_machine_yaml_documents_parse() -> None:
    paths = [
        ROOT / "config/profile.yaml",
        ROOT / "docs/30-constraints/rule-packs.yaml",
        ROOT / "docs/20-domain/playbooks/monthly-business-review/manifest.yaml",
    ]

    for path in paths:
        assert isinstance(yaml.safe_load(path.read_text(encoding="utf-8")), dict)
