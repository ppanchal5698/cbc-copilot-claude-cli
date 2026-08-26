#!/usr/bin/env python3
"""calc-engine MCP server - the only place quote arithmetic happens.

Formulas (confirmed, Requirements Matrix 5.0):
    Sale $ EA = Cost / (1 - margin)
    Unit      = Sale $ EA
    Ext       = Unit x Qty
    Sub-total = SUM(Ext) per group
    Grand tot = SUM(sub-totals)

Legacy "unit weight" is deliberately absent - it was removed in the 14 Jul session.
Margin bands: .claude/memory/margin_sheet.md
"""
from __future__ import annotations

import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _runtime import serve  # noqa: E402
from tools import TOOLS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MARGIN_FILE = ROOT / "reference-library" / "margins" / "margin_framework.json"

# Fallback if the reference library is missing; the JSON file is the source of truth.
DEFAULT_BANDS = {
    "commodity": 0.27,
    "restroom_partitions": 0.35,
    "specialty": 0.40,
    "custom_built": 0.25,
    "accessories": 0.56,
}

# Sales tax applies only where CBC has nexus (.claude/memory/sales_tax_rules.md).
TAX_RATES = {"OH": 0.08, "KY": 0.065}


def _money(value: float | Decimal) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _bands() -> dict[str, float]:
    if not MARGIN_FILE.exists():
        return dict(DEFAULT_BANDS)
    data = json.loads(MARGIN_FILE.read_text(encoding="utf-8"))
    bands = {b["key"]: float(b["margin"]) for b in data.get("bands", []) if "key" in b}
    if "accessories_derived" in data:
        bands["accessories"] = float(data["accessories_derived"])
    return bands or dict(DEFAULT_BANDS)


def calculate_line(cost: float, margin: float, quantity: float = 1) -> dict[str, Any]:
    if not 0 <= margin < 1:
        raise ValueError(f"margin must be a fraction in [0, 1), got {margin}")
    if cost < 0:
        raise ValueError(f"cost must not be negative, got {cost}")
    divisor = 1 - margin
    sale_ea = _money(Decimal(str(cost)) / Decimal(str(divisor)))
    return {
        "cost": _money(cost),
        "margin": margin,
        "divisor": round(divisor, 4),
        "quantity": quantity,
        "sale_ea": sale_ea,
        "unit_sale_ea": sale_ea,
        "ext_price": _money(Decimal(str(sale_ea)) * Decimal(str(quantity))),
        "formula": "sale_ea = cost / (1 - margin); ext_price = sale_ea * quantity",
    }


def apply_margin(
    cost: float,
    product_type: str,
    override_margin: float | None = None,
    override_reason: str | None = None,
) -> dict[str, Any]:
    bands = _bands()
    if product_type not in bands:
        raise ValueError(f"unknown product_type {product_type!r}; known: {sorted(bands)}")
    default_margin = bands[product_type]
    margin = default_margin if override_margin is None else float(override_margin)
    result = calculate_line(cost=cost, margin=margin, quantity=1)
    result.update(
        {
            "product_type": product_type,
            "default_margin": default_margin,
            "overridden": override_margin is not None,
            "override_reason": override_reason,
            "margin_check": validate_margin(product_type, margin),
        }
    )
    if override_margin is not None and not override_reason:
        result["warning"] = (
            "Margin overridden with no recorded reason - this is what the "
            "margin-governance flag exists for."
        )
    return result


def validate_margin(product_type: str, applied_margin: float) -> dict[str, Any]:
    bands = _bands()
    floor = bands.get(product_type)
    if floor is None:
        return {"status": "unknown_product_type", "product_type": product_type}
    below = applied_margin < floor - 1e-9
    return {
        "status": "fail" if below else "pass",
        "product_type": product_type,
        "floor": floor,
        "applied_margin": applied_margin,
        "flag": "below_band" if below else None,
        "note": "Flagged only. Approval routing is deferred (NFR-8).",
    }


def compute_totals(
    line_items: list[dict[str, Any]], project_state: str | None = None
) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for item in line_items:
        group = str(item.get("group") or "ungrouped")
        ext = item.get("ext_price")
        if ext is None:
            ext = float(item.get("sale_ea", 0)) * float(item.get("quantity", 1))
        bucket = groups.setdefault(group, {"group": group, "line_count": 0, "subtotal": 0.0})
        bucket["line_count"] += 1
        bucket["subtotal"] = _money(bucket["subtotal"] + float(ext))

    subtotal = _money(sum(g["subtotal"] for g in groups.values()))
    state = (project_state or "").upper()
    tax_rate = TAX_RATES.get(state, 0.0)
    tax = _money(subtotal * tax_rate)

    return {
        "groups": sorted(groups.values(), key=lambda g: g["group"]),
        "subtotal": subtotal,
        "freight": None,
        "freight_note": "TBD - freight is not quoted at estimate stage",
        "project_state": state or None,
        "tax_rate": tax_rate,
        "tax": tax,
        "tax_note": (
            "Sales tax applies to Ohio and Kentucky only; all other states and Canada are untaxed."
            if state
            else "Project state unknown - tax UNRESOLVED, flag for the estimator."
        ),
        "grand_total": _money(subtotal + tax),
    }


HANDLERS = {
    "calculate_line": calculate_line,
    "apply_margin": apply_margin,
    "compute_totals": compute_totals,
    "validate_margin": validate_margin,
}


def _demo() -> None:
    """Runnable check: the arithmetic that every quote depends on."""
    line = calculate_line(cost=74.33, margin=0.27, quantity=3)
    assert line["sale_ea"] == 101.82, line
    assert line["ext_price"] == 305.46, line

    totals = compute_totals(
        [
            {"group": "Door 01", "ext_price": 305.46},
            {"group": "Door 01", "sale_ea": 100.0, "quantity": 2},
            {"group": "Accessories", "ext_price": 50.0},
        ],
        project_state="OH",
    )
    assert totals["subtotal"] == 555.46, totals
    assert totals["tax"] == 44.44, totals
    assert totals["grand_total"] == 599.90, totals

    untaxed = compute_totals([{"group": "g", "ext_price": 100.0}], project_state="LA")
    assert untaxed["tax"] == 0.0 and untaxed["grand_total"] == 100.0, untaxed

    assert validate_margin("commodity", 0.20)["status"] == "fail"
    assert validate_margin("commodity", 0.27)["status"] == "pass"
    print("calc-engine demo OK")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        _demo()
    else:
        serve("calc-engine", TOOLS, HANDLERS)
