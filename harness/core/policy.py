"""Scope-aware policy checks. SQL parsing stays out of this module."""

from __future__ import annotations

from typing import Any

_SCOPE_RANK = {"all": 0, "domain": 1, "platform": 2, "playbook": 3}


class PolicyError(ValueError):
    """Rules in the same scope disagree, or a call is outside the allowlist."""


def compose_rules(packs: dict[str, Any], selected: list[str]) -> dict[str, str]:
    """Return rule id to winning pack. Same-scope duplicates block."""
    winners: dict[str, str] = {}
    scopes: dict[str, str] = {}
    for pack_id in selected:
        pack = packs[pack_id]
        scope = str(pack["scope"])
        for rule_id in pack["rules"]:
            if rule_id in winners and scopes[rule_id] == scope and winners[rule_id] != pack_id:
                raise PolicyError(f"same-scope conflict: {rule_id}")
            if rule_id not in winners or _SCOPE_RANK[scope] >= _SCOPE_RANK[scopes[rule_id]]:
                winners[rule_id] = pack_id
                scopes[rule_id] = scope
    return winners


class Policy:
    def __init__(self, allowlist: set[str]) -> None:
        self._allowlist = set(allowlist)

    def check(self, event: dict[str, Any]) -> str:
        """Allow a tool call, or reject network and restricted egress."""
        capability = str(event.get("capability", ""))
        wants_network = bool(event.get("network", False))
        classification = str(event.get("classification", "internal"))
        if wants_network and capability not in self._allowlist:
            raise PolicyError("network denied")
        if wants_network and classification == "restricted":
            raise PolicyError("restricted artifact cannot leave the runtime")
        if capability and capability not in self._allowlist and event.get("enforce_capability"):
            raise PolicyError("capability is not allowlisted")
        return "allow"
