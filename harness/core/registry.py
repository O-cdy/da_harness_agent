"""Strict loader for playbook manifests, rule packs, and profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_REQUIRED_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "id",
        "contract_version",
        "platform_selection",
        "core_capabilities",
        "optional_capabilities",
        "steps",
        "metric_refs",
        "metric_availability",
        "skill_refs",
        "rule_packs",
        "time_scope",
        "source_readiness",
        "unsupported_policy",
        "report_policy",
        "outline",
        "approval_policy",
        "eval_overlays",
    }
)


class RegistryError(ValueError):
    """A machine contract was missing, duplicated, or not executable."""


def load_document(path: Path) -> dict[str, Any]:
    """Load one YAML or JSON object. Markdown is never a machine contract."""
    if path.suffix.lower() in {".md", ".markdown"}:
        raise RegistryError(f"refusing to derive a contract from markdown: {path.name}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        import json

        payload = json.loads(text)
    else:
        payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise RegistryError("machine contract must be an object")
    return payload


class Registry:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _read(self, relative_path: str) -> dict[str, Any]:
        path = (self._root / relative_path).resolve()
        if not path.is_relative_to(self._root.resolve()):
            raise RegistryError("contract path escapes the registry root")
        return load_document(path)

    def load_manifest(self, relative_path: str) -> dict[str, Any]:
        document = self._read(relative_path)
        if document.get("schema_version") != 1:
            raise RegistryError("unknown manifest schema_version")
        missing = sorted(_REQUIRED_MANIFEST_FIELDS - set(document))
        if missing:
            raise RegistryError(f"manifest missing fields: {missing}")
        step_ids = [step.get("step_id") for step in document["steps"]]
        if len(step_ids) != len(set(step_ids)):
            raise RegistryError("duplicate step_id")
        return document

    def load_rule_packs(self, relative_path: str) -> dict[str, Any]:
        document = self._read(relative_path)
        if document.get("schema_version") != 1:
            raise RegistryError("unknown rule-pack schema_version")
        packs = document.get("packs")
        if not isinstance(packs, dict) or not packs:
            raise RegistryError("rule packs must be a non-empty object")
        for name, pack in packs.items():
            rules = pack.get("rules", [])
            if len(rules) != len(set(rules)):
                raise RegistryError(f"duplicate rule id in {name}")
        return document

    def load_profile(self, relative_path: str) -> dict[str, Any]:
        document = self._read(relative_path)
        if not isinstance(document.get("schema_version"), int):
            raise RegistryError("unknown profile schema_version")
        return document

    def materialize(
        self,
        manifest: dict[str, Any],
        rule_packs: dict[str, Any],
        target_platforms: list[str],
    ) -> dict[str, Any]:
        """Inline capability and rule-pack references. Dangling refs are rejected."""
        selection = manifest["platform_selection"]
        if selection.get("mode") == "explicit" and not target_platforms:
            raise RegistryError("explicit platform selection requires target platforms")
        packs = rule_packs["packs"]
        effective: list[str] = []
        for pack_id in manifest["rule_packs"]["fixed"]:
            if pack_id not in packs:
                raise RegistryError(f"dangling rule pack: {pack_id}")
            effective.append(pack_id)
        for platform_id in target_platforms:
            pack_id = f"platform:{platform_id}"
            if pack_id not in packs:
                raise RegistryError(f"dangling rule pack: {pack_id}")
            effective.append(pack_id)
        return {
            "playbook_id": manifest["id"],
            "core_capabilities": list(manifest["core_capabilities"]),
            "effective_rule_packs": effective,
            "target_platforms": list(target_platforms),
        }
