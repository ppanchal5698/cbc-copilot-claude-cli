#!/usr/bin/env python3
"""p21-connector MCP server - READ-ONLY last-PO cost lookup.

Cost path 1 of three (.claude/memory/cost_sourcing_rules.md).

There are no write tools in this module. That is the guardrail, not an oversight
(NFR-5, .claude/rules/p21-read-only.md).

P21 is not integrated yet (NR-10 - feasibility under investigation). Until
P21_BASE_URL is set, every lookup returns a structured "manual entry required"
response with a refresh prompt. It never invents a price.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _runtime import serve  # noqa: E402
from tools import TOOLS  # noqa: E402

# Freshness thresholds, in days (Requirements Matrix 6.2).
FRESH_DAYS = 180  # under ~6 months
UNRELIABLE_DAYS = 240  # ~6-8 months and beyond
STALE_DAYS = 1095  # 3 years - discard

BASE_URL = os.environ.get("P21_BASE_URL", "").strip()

MANUAL_ENTRY = {
    "connected": False,
    "cost": None,
    "cost_source": "MANUAL",
    "action_required": "manual_price_entry",
    "prompt": "price may be out of date - refresh",
    "reason": (
        "P21 is not connected in this environment. Integration feasibility and a "
        "part-number / semi-item matching strategy are still open (NR-10)."
    ),
    "fallbacks": [
        "Path 2: vendor list price x multiplier tier (pricebook MCP server)",
        "Path 3: distributor lookup (Banner Solutions, SecLock, J2) or vendor RFQ",
    ],
}


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def check_freshness(po_date: str) -> dict[str, Any]:
    try:
        purchased = _parse_date(po_date)
    except ValueError as exc:
        raise ValueError(f"po_date must be an ISO date, got {po_date!r}") from exc

    age = (date.today() - purchased).days
    if age < 0:
        status, usable, guidance = "future_dated", False, "PO date is in the future - verify."
    elif age <= FRESH_DAYS:
        status, usable, guidance = "fresh", True, "Usable if there has been no price increase."
    elif age <= UNRELIABLE_DAYS:
        status, usable, guidance = (
            "unreliable",
            False,
            "About 6-8 months old - re-verify against the vendor sheet before quoting.",
        )
    elif age <= STALE_DAYS:
        status, usable, guidance = (
            "unreliable",
            False,
            "Well past the freshness window - re-verify or price by list x multiplier.",
        )
    else:
        status, usable, guidance = "stale", False, "3+ years old - discard. Do not quote from this."

    return {
        "po_date": po_date,
        "age_days": age,
        "freshness_status": status,
        "usable": usable,
        "guidance": guidance,
        "rule": "under ~6 months fresh; ~6-8 months+ unreliable; 3-4 years discard",
    }


def lookup_last_po(part_number: str, vendor: str | None = None) -> dict[str, Any]:
    if not BASE_URL:
        return {
            "part_number": part_number,
            "vendor": vendor,
            "last_po_price": None,
            "po_date": None,
            "freshness_status": "unknown",
            "item_id": None,
            **MANUAL_ENTRY,
        }

    # ponytail: no live client until CBC IT confirms the P21 endpoint and auth shape.
    # Wire the read-only query here; keep the MANUAL_ENTRY contract for every failure
    # path so a pricing agent never sees a half-answer.
    return {
        "part_number": part_number,
        "vendor": vendor,
        "connected": True,
        "error": "P21_BASE_URL is set but no read client is implemented yet (NR-10).",
        **MANUAL_ENTRY,
    }


def search_item(query: str, limit: int = 10) -> dict[str, Any]:
    return {
        "query": query,
        "limit": limit,
        "connected": bool(BASE_URL),
        "results": [],
        "known_risks": [
            "P21 item IDs frequently differ from manufacturer part numbers.",
            "Semi-custom items will not match at all.",
            "Manual cost entry must always remain available.",
        ],
        **({} if BASE_URL else {"note": MANUAL_ENTRY["reason"]}),
    }


HANDLERS = {
    "lookup_last_po": lookup_last_po,
    "check_freshness": check_freshness,
    "search_item": search_item,
}

# Guardrail: assert at import time that nothing mutating ever creeps in.
_FORBIDDEN = ("write", "update", "insert", "post", "create", "delete", "set_")
assert not [t for t in TOOLS if any(word in t["name"].lower() for word in _FORBIDDEN)], (
    "p21-connector must expose no write tools (NFR-5)"
)


def _demo() -> None:
    """Runnable check: the freshness bands and the never-guess contract."""
    assert check_freshness(date.today().isoformat())["freshness_status"] == "fresh"
    old = (date.today().replace(year=date.today().year - 2)).isoformat()
    assert check_freshness(old)["usable"] is False
    ancient = (date.today().replace(year=date.today().year - 5)).isoformat()
    assert check_freshness(ancient)["freshness_status"] == "stale"

    result = lookup_last_po("3510", "hager")
    assert result["last_po_price"] is None and result["cost_source"] == "MANUAL"
    print("p21-connector demo OK -", json.dumps(result["prompt"]))


if __name__ == "__main__":
    if "--demo" in sys.argv:
        _demo()
    else:
        serve("p21-connector", TOOLS, HANDLERS)
