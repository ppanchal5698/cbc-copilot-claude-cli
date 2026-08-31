"""Quote arithmetic - the only place money math happens in this system.

Formulas (confirmed, Requirements Matrix 5.0):
    Sale $ EA = Cost / (1 - margin)
    Unit      = Sale $ EA
    Ext       = Unit x Qty
    Sub-total = SUM(Ext) per group
    Grand tot = SUM(sub-totals)

Legacy "unit weight" is deliberately absent - it was removed in the 14 Jul session.
Margin bands: .claude/memory/margin_sheet.md

This lives here rather than inside the calc-engine MCP server because both the
server and the API need it, and the API used to get at it by exec-ing the
server's module through a custom loader and calling a private function. Same
arithmetic, one implementation, no transport in the middle: `mcp-servers/
calc-engine/server.py` is now an adapter over this module.
"""
from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MARGIN_FILE = ROOT / "reference-library" / "margins" / "margin_framework.json"
TAX_FILE = ROOT / "reference-library" / "tax" / "sales_tax_rates.json"

# Fallback if the reference library is missing; the JSON file is the source of truth.
DEFAULT_BANDS = {
    "commodity": 0.27,
    "restroom_partitions": 0.35,
    "specialty": 0.40,
    "custom_built": 0.25,
    "accessories": 0.56,
}

# Sales tax applies only where CBC has nexus (.claude/memory/sales_tax_rules.md).
# The JSON file is the source of truth; this is the fallback if it is missing.
DEFAULT_TAX_RATES = {"OH": 0.08, "KY": 0.065}


def _money(value: float | Decimal) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _file_signature(path: Path) -> tuple[int, int]:
    """Cache key for a reference file: (mtime, size).

    mtime alone missed a second edit that landed inside the same filesystem tick -
    a real risk for scripted or back-to-back updates, not just tests. Size moves
    whenever the row set does, so an add or remove is always seen; a same-length
    value edit within one tick is the only gap left, and no human UI writes that fast.
    """
    stat = path.stat()
    return (stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=4)
def _bands_at(_signature: tuple[int, int]) -> dict[str, float]:
    data = json.loads(MARGIN_FILE.read_text(encoding="utf-8"))
    bands = {b["key"]: float(b["margin"]) for b in data.get("bands", []) if "key" in b}
    if "accessories_derived" in data:
        bands["accessories"] = float(data["accessories_derived"])
    return bands or dict(DEFAULT_BANDS)


def bands() -> dict[str, float]:
    """The margin bands, re-read only when the file actually changes.

    This is called twice per line by the API's re-price loop and once per product
    by catalog search, and it used to stat, read and JSON-parse the file every
    single time: a 500-line quote did roughly a thousand synchronous file reads
    on the event loop, on every page load, and again every four seconds while a
    job was running. Keying the cache on mtime keeps an edited file picked up
    without a restart.
    """
    try:
        signature = _file_signature(MARGIN_FILE)
    except OSError:
        return dict(DEFAULT_BANDS)
    # Copied on the way out: the cached dict is shared by every caller.
    return dict(_bands_at(signature))


@lru_cache(maxsize=4)
def _tax_rates_at(_signature: tuple[int, int]) -> dict[str, float]:
    data = json.loads(TAX_FILE.read_text(encoding="utf-8"))
    # A present-but-empty table means "no nexus anywhere", so honour it verbatim;
    # only a structurally broken file (no rates key) falls back to the default.
    if "rates" not in data:
        return dict(DEFAULT_TAX_RATES)
    return {str(code).upper(): float(rate) for code, rate in (data["rates"] or {}).items()}


def tax_rates() -> dict[str, float]:
    """Nexus tax rates, re-read only when the file changes (see bands())."""
    try:
        signature = _file_signature(TAX_FILE)
    except OSError:
        return dict(DEFAULT_TAX_RATES)
    return dict(_tax_rates_at(signature))


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
    known = bands()
    if product_type not in known:
        raise ValueError(f"unknown product_type {product_type!r}; known: {sorted(known)}")
    default_margin = known[product_type]
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
    floor = bands().get(product_type)
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


def _line_ext_price(item: dict[str, Any]) -> float:
    """Roll-up price for one line; null sale_ea/ext_price count as unpriced (0)."""
    ext = item.get("ext_price")
    if ext is not None:
        try:
            return float(ext)
        except (TypeError, ValueError):
            return 0.0
    sale = item.get("sale_ea")
    if sale is None:
        return 0.0
    try:
        qty = item.get("quantity", 1)
        return float(sale) * float(qty)
    except (TypeError, ValueError):
        return 0.0


def compute_totals(
    line_items: list[dict[str, Any]], project_state: str | None = None
) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for item in line_items:
        group = str(item.get("group") or "ungrouped")
        ext = _line_ext_price(item)
        bucket = groups.setdefault(group, {"group": group, "line_count": 0, "subtotal": 0.0})
        bucket["line_count"] += 1
        bucket["subtotal"] = _money(bucket["subtotal"] + ext)

    subtotal = _money(sum(g["subtotal"] for g in groups.values()))
    state = (project_state or "").upper()
    tax_rate = tax_rates().get(state, 0.0)
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
