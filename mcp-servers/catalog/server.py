#!/usr/bin/env python3
"""catalog MCP server - product search over the SQLite FTS5 index.

READ-ONLY by design, like p21-connector, and now read-only in a way the database
enforces rather than a convention: the connection is opened `query_only`.

This used to read MongoDB, and its sibling `pricebook` server answered the same
questions by opening every PDF and running difflib over every line - 6 s on a cold
process, 2.5 s warm, paid again on every run because each run gets a fresh MCP
subprocess. Search now costs a fraction of a millisecond, because the reading
happened once, in the background, when the catalog was uploaded.

The vendor PDFs remain the source of truth. This index is derived from them and can
be thrown away and rebuilt: `python -m catalog_index.rebuild`.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mcp-servers"))

from _runtime import serve  # noqa: E402
from tools import TOOLS  # noqa: E402

from catalog_index import db as index_db  # noqa: E402
from catalog_index import search as index_search  # noqa: E402

TIERS_FILE = ROOT / "reference-library" / "multipliers" / "vendor_tiers.json"
SPECIAL_NETS_FILE = ROOT / "reference-library" / "multipliers" / "hager_special_nets.json"
STALE_DAYS = 180

_special_nets: dict[str, dict[str, Any]] | None = None
_special_nets_meta: dict[str, Any] | None = None
STOCK_LIST_DIR = ROOT / "reference-library" / "hardware_sets"

# A tool call must not be able to ask for an unbounded scan, and must not hang a
# pricing pass if it tries. The cap is enforced here as well as in the query, and
# the progress handler aborts a runaway statement rather than blocking the run.
MAX_LIMIT = 50
QUERY_TIMEOUT_SECONDS = 5.0

_connection: sqlite3.Connection | None = None
_deadline = {"at": 0.0}


def _db() -> sqlite3.Connection:
    """One read-only connection for the life of the process."""
    global _connection
    if _connection is None:
        path = index_db.index_path()
        if not path.exists():
            raise FileNotFoundError(
                f"the catalog index does not exist at {path}. Build it with "
                "`python -m catalog_index.rebuild` - it is derived from pricebooks/ "
                "and takes about 20 seconds."
            )
        _connection = index_db.connect(path, readonly=True)
        _connection.set_progress_handler(
            lambda: 1 if _deadline["at"] and time.monotonic() > _deadline["at"] else 0,
            100_000,
        )
    return _connection


def _bounded() -> sqlite3.Connection:
    connection = _db()
    _deadline["at"] = time.monotonic() + QUERY_TIMEOUT_SECONDS
    return connection


def _clamp(limit: Any, default: int = 10) -> int:
    try:
        return max(1, min(int(limit), MAX_LIMIT))
    except (TypeError, ValueError):
        return default


# ── search ─────────────────────────────────────────────────────────────────


def search_products(
    query: str,
    vendor: str | None = None,
    catalog_id: str | None = None,
    category: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> dict[str, Any]:
    if not str(query or "").strip():
        return {"error": "query is required", "count": 0, "results": []}
    try:
        start = max(0, int(offset or 0))
    except (TypeError, ValueError):
        start = 0
    return index_search.search(
        _bounded(), str(query), vendor=vendor, catalog_id=catalog_id,
        category=category, limit=_clamp(limit), offset=start,
    )


def search_catalog(catalog_id: str, query: str, limit: int = 10) -> dict[str, Any]:
    return search_products(query, catalog_id=catalog_id, limit=limit)


def get_product_details(
    product_id: int | None = None,
    product_code: str | None = None,
    vendor: str | None = None,
) -> dict[str, Any]:
    if product_id is None and not product_code:
        return {"error": "give product_id, or product_code (optionally with vendor)"}
    found = index_search.get_product(
        _bounded(), product_id=product_id, product_code=product_code, vendor=vendor
    )
    if found is None:
        return {
            "found": False,
            "note": "Not in the index. Price manually, or check whether that catalog is "
                    "indexed with list_catalogs - do not substitute a similar part.",
        }
    return {"found": True, "product": found}


def list_catalogs(vendor: str | None = None) -> dict[str, Any]:
    from datetime import date

    rows = index_search.list_catalogs(_bounded(), vendor)
    for row in rows:
        effective = row.get("effective_date")
        age = None
        if effective:
            try:
                age = (date.today() - date.fromisoformat(effective)).days
            except (ValueError, TypeError):
                age = None
        row["ageDays"] = age
        row["stale"] = age is not None and age > STALE_DAYS
        row["undated"] = effective is None

    ready = [r for r in rows if r["status"] == "ready"]
    return {
        "count": len(rows),
        "searchable": len(ready),
        "products": sum(r["product_count"] for r in ready),
        "catalogs": rows,
        "stale": sum(1 for r in rows if r["stale"]),
        "note": (
            "Only catalogs with status 'ready' appear in search results. "
            "NFR-10 is open - no named owner or refresh cadence; age is the only signal."
        ),
    }


def get_catalog_status(catalog_id: str) -> dict[str, Any]:
    from catalog_index import registry

    found = registry.status_of(_bounded(), catalog_id)
    if found is None:
        return {"found": False, "catalog_id": catalog_id, "note": "no such catalog"}
    return {"found": True, **found}


# ── multipliers: curated data, not extracted ───────────────────────────────


def _load_special_nets() -> dict[str, dict[str, Any]]:
    """Part number → special net row for vendors that publish fixed net overrides."""
    global _special_nets, _special_nets_meta
    if _special_nets is not None:
        return _special_nets

    by_part: dict[str, dict[str, Any]] = {}
    meta: dict[str, Any] = {}
    if SPECIAL_NETS_FILE.exists():
        payload = json.loads(SPECIAL_NETS_FILE.read_text(encoding="utf-8"))
        meta = {
            "vendor": payload.get("vendor", "hager"),
            "effective_date": payload.get("effective_date"),
            "source": payload.get("source"),
        }
        for row in payload.get("items", []):
            part = str(row.get("part_number", "")).strip().upper()
            if part:
                by_part[part] = {**row, "vendor": meta["vendor"]}
    _special_nets = by_part
    _special_nets_meta = meta
    return by_part


def _part_lookup_keys(part_number: str) -> set[str]:
    upper = str(part_number or "").strip().upper()
    if not upper:
        return set()
    keys = {upper}
    keys.add(upper.split("-")[0].split()[0])
    return keys


def get_special_net(vendor: str, part_number: str) -> dict[str, Any] | None:
    """Fixed net price from the multiplier sheet, when one exists for this part."""
    vendor_key = str(vendor or "").strip().lower()
    if vendor_key != "hager":
        return None
    nets = _load_special_nets()
    for key in _part_lookup_keys(part_number):
        if key in nets:
            row = nets[key]
            return {
                "vendor": vendor_key,
                "part_number": key,
                "net_price": row["net_price"],
                "item_code": row.get("item_code"),
                "section": row.get("section"),
                "source_page": row.get("source_page"),
                "effective_date": (_special_nets_meta or {}).get("effective_date"),
                "source": (_special_nets_meta or {}).get("source"),
            }
    return None


def is_stock_item(vendor: str, part_number: str) -> dict[str, Any]:
    """NR-6 top-10 stock list lookup."""
    vendor_key = str(vendor or "").strip().lower()
    path = STOCK_LIST_DIR / f"{vendor_key}_top10_stock.json"
    if not path.exists():
        return {
            "vendor": vendor_key,
            "part_number": part_number,
            "stock": None,
            "note": "No top-10 stock list on file for this vendor (NR-6 pending).",
        }

    payload = json.loads(path.read_text(encoding="utf-8"))
    needle = part_number.strip().upper()
    base = needle.split("-")[0].split()[0]
    parts = {
        str(item.get("part_number", "")).strip().upper()
        for item in payload.get("items", [])
        if item.get("part_number")
    }
    matched = needle in parts or base in parts
    return {
        "vendor": vendor_key,
        "part_number": part_number,
        "stock": matched,
        "list_status": payload.get("status"),
        "status_note": payload.get("status_note"),
        "source": payload.get("source"),
    }


def get_multiplier(vendor: str, category: str | None = None) -> dict[str, Any]:
    """From the tier sheet purchasing maintains. Never inferred from a PDF."""
    if not TIERS_FILE.exists():
        return {"vendor": vendor, "multiplier": None, "note": "vendor_tiers.json not found"}

    data = json.loads(TIERS_FILE.read_text(encoding="utf-8"))
    needle = str(vendor or "").strip().lower()
    for record in data.get("vendors", []):
        names = {str(record.get("key", "")).lower(), str(record.get("name", "")).lower()}
        if needle not in names and needle not in str(record.get("name", "")).lower():
            continue
        categories = record.get("categories") or {}
        if category and categories:
            key = str(category).strip().lower().replace(" ", "_").replace("-", "_")
            if key in categories:
                return {
                    "vendor": record.get("name"), "category": key,
                    "multiplier": categories[key], "effective_date": record.get("effective_date"),
                    "account": record.get("account"), "source": record.get("source"),
                }
            return {
                "vendor": record.get("name"), "category": category, "multiplier": None,
                "available_categories": sorted(categories),
                "note": "Unknown category for this vendor - do not guess, ask the estimator.",
            }
        return {
            "vendor": record.get("name"), "tier": record.get("tier"),
            "multiplier": record.get("multiplier"), "categories": categories or None,
            "effective_date": record.get("effective_date"), "account": record.get("account"),
            "note": record.get("note"), "source": record.get("source"),
        }
    return {
        "vendor": vendor, "multiplier": None,
        "note": "Vendor not in the tier sheet. Price manually (MANUAL cut-off) - never guess.",
    }


# ── compatibility: the names the agents and skills already call ────────────


def search_product(
    query: str, vendor: str | None = None, division: str | None = None, limit: int = 10
) -> dict[str, Any]:
    """Alias kept so `.claude/agents/` and `.claude/skills/` keep working."""
    result = search_products(query, vendor=vendor, limit=limit)
    result["hits"] = [
        {
            "vendor": r["vendor"], "source_file": r["source_file"],
            "source_page": r["page_number"], "effective_date": r["effective_date"],
            "line": " ".join(str(p) for p in (r["product_code"], r["product_name"]) if p)[:200],
            "price": r["price"], "score": r["relevance_score"],
        }
        for r in result.get("results", [])
    ]
    result["hit_count"] = result.get("count", 0)
    return result


def list_vendors() -> dict[str, Any]:
    """Alias of list_catalogs, grouped the way the old tool reported it."""
    catalogs = list_catalogs()
    by_vendor: dict[str, dict[str, Any]] = {}
    for row in catalogs["catalogs"]:
        entry = by_vendor.setdefault(
            row["vendor"], {"vendor": row["vendor"], "catalogs": [], "products": 0}
        )
        entry["catalogs"].append(
            {"catalog_id": row["catalog_id"], "file": row["file_name"],
             "status": row["status"], "effective_date": row["effective_date"],
             "products": row["product_count"], "stale": row["stale"]}
        )
        entry["products"] += row["product_count"]
    return {
        "count": len(by_vendor),
        "vendors": sorted(by_vendor.values(), key=lambda v: v["vendor"]),
        # The flat per-book list the previous server returned. Kept because the
        # agents, skills and tests that call this tool read `pricebooks`, and a
        # rename would break them silently at the moment they most need a price.
        "pricebooks": [
            {
                "vendor": row["vendor"], "name": row["file_name"], "file": row["file_name"],
                "catalog_id": row["catalog_id"], "effective_date": row["effective_date"],
                "status": row["status"], "products": row["product_count"],
                "stale": row["stale"],
            }
            for row in catalogs["catalogs"]
        ],
    }


def lookup_pricing(part_number: str, vendor: str, category: str | None = None) -> dict[str, Any]:
    """List price and net cost for an exact part. Ambiguity is reported, not resolved."""
    found = search_products(part_number, vendor=vendor, limit=MAX_LIMIT)
    matches = [
        {
            "vendor": r["vendor"], "product_code": r["product_code"],
            "description": r["product_name"], "list_price": r["price"],
            "source_file": r["source_file"], "source_page": r["page_number"],
            "effective_date": r["effective_date"],
        }
        for r in found.get("results", [])
        if r["product_code"]
    ]
    priced = [m for m in matches if m["list_price"] is not None]

    special = get_special_net(vendor, part_number)
    tier = get_multiplier(vendor, category)
    multiplier = tier.get("multiplier")
    list_price = net_cost = None
    cost_source = "MANUAL"
    note = (
        "Ambiguous, unpriced or missing - the estimator prices this line. "
        "Adders (electrification, NRP, premium finish) are never included here."
    )

    if special is not None:
        net_cost = float(special["net_price"])
        cost_source = "SPECIAL_NET"
        note = (
            f"Special net from the Hager multiplier sheet (item {special.get('item_code')}, "
            f"p {special.get('source_page')}). Overrides list × category."
        )
        if len(priced) == 1:
            list_price = priced[0]["list_price"]
    elif len(priced) == 1 and isinstance(multiplier, (int, float)):
        list_price = priced[0]["list_price"]
        net_cost = round(float(list_price) * float(multiplier), 2)
        cost_source = "LIST_X_MULTIPLIER"
        note = "Unambiguous single match priced at list x multiplier."

    return {
        "part_number": part_number, "vendor": vendor,
        "match_count": len(matches), "matches": matches[:10],
        "multiplier": multiplier, "multiplier_tier": tier.get("tier"),
        "multiplier_effective_date": tier.get("effective_date"),
        "special_net": special,
        "list_price": list_price, "net_cost": net_cost,
        "cost_source": cost_source,
        "note": note,
    }


HANDLERS = {
    "search_products": search_products,
    "search_catalog": search_catalog,
    "get_product_details": get_product_details,
    "list_catalogs": list_catalogs,
    "get_catalog_status": get_catalog_status,
    "get_multiplier": get_multiplier,
    "get_special_net": get_special_net,
    "is_stock_item": is_stock_item,
    "search_product": search_product,
    "list_vendors": list_vendors,
    "lookup_pricing": lookup_pricing,
}

# Guardrail: this server reads. Nothing here may ever write to the catalog, and the
# connection is opened query_only so the database refuses even if this slips.
_FORBIDDEN = ("write", "update", "insert", "upsert", "delete", "create", "set_")
assert not [t for t in TOOLS if any(word in t["name"].lower() for word in _FORBIDDEN)], (
    "catalog must expose no write tools"
)


def _demo() -> None:
    """Runnable check against the real index."""
    catalogs = list_catalogs()
    assert catalogs["searchable"] > 0, "no catalogs indexed - run catalog_index.rebuild"

    hit = search_products("B-2888")
    assert hit["count"] >= 1, hit
    assert hit["results"][0]["product_code"] == "B-2888", hit["results"][0]

    miss = search_products("definitely-not-a-real-part-xyz")
    assert miss["count"] == 0 and "MANUAL cut-off" in miss["note"]

    assert get_multiplier("acme")["multiplier"] is None
    print(
        f"catalog demo OK - {catalogs['searchable']} catalogs, "
        f"{catalogs['products']} products, {catalogs['stale']} stale"
    )


if __name__ == "__main__":
    if "--demo" in sys.argv:
        _demo()
    else:
        serve("catalog", TOOLS, HANDLERS)
