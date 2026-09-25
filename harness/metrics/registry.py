"""Canonical metric calculations. Formulas follow docs/20-domain/metrics.md section A."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

_EXCLUSIONS = ("cancelled", "sample", "noncommercial_gift", "gift")
_NATIVE_CHANNELS = frozenset({"affiliate", "live"})
_STATES = frozenset({"canonical", "platform-native", "provisional", "diagnostic"})


class MetricError(ValueError):
    """A metric id is unknown or its inputs are not usable."""


def compute(metric_id: str, facts: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Compute one canonical metric. The same facts always return the same text."""
    if metric_id not in {"M101", "M102", "M103", "M104", "M105", "M106", "M207a", "M207b"}:
        raise MetricError(f"metric is not in the canonical registry: {metric_id}")
    sales = [fact for fact in facts if _is_sale(fact)]
    gross = _sum(sales, "item_gross_amount")
    net = gross + _sum(sales, "seller_discount_amount") + _refund_effect(facts)
    orders = len(
        {(str(fact["platform"]), str(fact["account_id"]), str(fact["order_id"])) for fact in sales}
    )
    units = _sum(sales, "commercial_quantity")
    values = {
        "M101": gross,
        "M102": net,
        "M103": Decimal(orders),
        "M104": units,
        "M105": _ratio(net, Decimal(orders)),
        "M106": _ratio(net, units),
        "M207a": _ratio(_matched_refund(facts, "refund_item_subtotal"), net),
        "M207b": _quantity_rate(facts, units),
    }
    value = values[metric_id]
    if value is None:
        return {"metric_id": metric_id, "status": "diagnostic", "value": None}
    return {"metric_id": metric_id, "status": "canonical", "value": format(value, "f")}


def separate_state(state: str, value: str | None) -> dict[str, object]:
    """Keep non-canonical states out of the canonical total."""
    if state not in _STATES or state == "canonical":
        raise MetricError("state must stay outside the canonical total")
    return {"status": state, "value": value, "in_canonical_total": False}


def unmapped_products(facts: Sequence[Mapping[str, object]]) -> list[str]:
    """Park sale rows that have no product identity. Site totals still include them."""
    parked: list[str] = []
    for fact in facts:
        if _is_sale(fact) and not fact.get("product_identity"):
            parked.append(str(fact["order_id"]))
    return parked


def _is_sale(fact: Mapping[str, object]) -> bool:
    if any(bool(fact.get(flag)) for flag in _EXCLUSIONS):
        return False
    if str(fact.get("channel", "store")) in _NATIVE_CHANNELS:
        return False
    return "item_gross_amount" in fact


def _sum(facts: Sequence[Mapping[str, object]], key: str) -> Decimal:
    total = Decimal(0)
    for fact in facts:
        if key in fact and fact[key] is not None:
            total += _decimal(fact[key])
    return total


def _refund_effect(facts: Sequence[Mapping[str, object]]) -> Decimal:
    total = Decimal(0)
    for fact in facts:
        if fact.get("refund_matched") is False:
            continue
        if "refund_net_effect" in fact and fact["refund_net_effect"] is not None:
            total += _decimal(fact["refund_net_effect"])
    return total


def _matched_refund(facts: Sequence[Mapping[str, object]], key: str) -> Decimal:
    total = Decimal(0)
    for fact in facts:
        if fact.get("refund_matched") is False or key not in fact or fact[key] is None:
            continue
        total += _decimal(fact[key])
    return total


def _quantity_rate(facts: Sequence[Mapping[str, object]], units: Decimal) -> Decimal | None:
    for fact in facts:
        if fact.get("refund_matched") is False:
            continue
        if "refund_item_subtotal" in fact and fact.get("refund_quantity") is None:
            return None
    return _ratio(_matched_refund(facts, "refund_quantity"), units)


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, str, Decimal)):
        raise MetricError("numeric field has an unsupported type")
    return Decimal(value)
