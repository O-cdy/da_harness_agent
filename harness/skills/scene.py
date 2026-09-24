"""Scenario skills. They accept canonical facts and do not know a playbook id."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal


class SkillError(ValueError):
    """A skill input cannot produce an attributable result."""


def price_volume(
    previous_quantity: Decimal,
    previous_price: Decimal,
    current_quantity: Decimal,
    current_price: Decimal,
) -> dict[str, str]:
    """Split a change into volume, price, and residual. The three terms close."""
    delta = current_quantity * current_price - previous_quantity * previous_price
    volume = (current_quantity - previous_quantity) * previous_price
    price = previous_quantity * (current_price - previous_price)
    residual = (current_quantity - previous_quantity) * (current_price - previous_price)
    if abs(volume + price + residual - delta) > Decimal("0.000001"):
        raise SkillError("price-volume terms do not close")
    return {
        "volume": format(volume, "f"),
        "price": format(price, "f"),
        "residual": format(residual, "f"),
    }


def contribution(slices: Sequence[tuple[str, Decimal]], total: Decimal) -> dict[str, str]:
    """Require mutually exclusive slices to add back to the total change."""
    names = [name for name, _value in slices]
    if len(names) != len(set(names)):
        raise SkillError("contribution slices overlap")
    if "unmapped" not in names:
        raise SkillError("unmapped bucket is required")
    amount = sum((value for _name, value in slices), Decimal(0))
    if amount != total:
        raise SkillError("contribution slices are not additive")
    ordered = sorted(slices, key=lambda item: abs(item[1]), reverse=True)
    return {name: format(value, "f") for name, value in ordered}


def detect_anomalies(
    points: Sequence[str],
    calendar: Sequence[str] | None,
) -> dict[str, object]:
    """Annotate anomalies. A missing calendar is reported and does not fail the run."""
    if calendar is None:
        return {
            "calendar_missing": True,
            "points": [{"at": point, "in_promo_window": None} for point in points],
        }
    windows = set(calendar)
    return {
        "calendar_missing": False,
        "points": [{"at": point, "in_promo_window": point in windows} for point in points],
    }


def native_analysis(fact: Mapping[str, object]) -> dict[str, object]:
    """Return a platform-native result. It is never marked as part of a canonical total."""
    required = ("platform", "native_metric_id", "official_source", "region", "definition_version")
    missing = [key for key in required if not fact.get(key)]
    if missing:
        raise SkillError("native analysis is missing required metadata")
    return {
        "platform": fact["platform"],
        "native_metric_id": fact["native_metric_id"],
        "official_source": fact["official_source"],
        "region": fact["region"],
        "definition_version": fact["definition_version"],
        "status": "platform-native",
        "in_canonical_total": False,
    }
