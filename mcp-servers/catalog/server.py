#!/usr/bin/env python3
"""catalog MCP server - navigate the vendor price books, do not pre-digest them.

This used to serve product rows out of a SQLite FTS index built by extracting
every line of every catalog. Vendor catalogs are too irregular for that: 37.8% of
the codes it produced contained no letter at all, 183 dates were recorded as part
numbers, one vendor's sheet yielded nothing while reporting success, and a
pricing pass reading those rows had no way to tell a misread number from a real
one.

It now reads a page index: a two-line description of every page of every catalog,
in MongoDB, with the part families on it and whether it carries prices. The tools
answer "which page" - and the price comes off that page, read with pdf-tools
during the run that quotes it.

Nothing here returns a price. That is the design, not an omission.

READ-ONLY, and enforced rather than promised: the connection uses
MONGODB_READONLY_URI and refuses to fall back to the writable string.
"""
from __future__ import annotations

import copy
import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "mcp-servers"))

from _runtime import serve  # noqa: E402
from tools import TOOLS  # noqa: E402

from cbc.pageindex import basis as price_basis_of  # noqa: E402
from cbc.pageindex import models as page_models  # noqa: E402
from cbc.pageindex import query as page_query  # noqa: E402
from cbc.pageindex import reader  # noqa: E402

from cbc.services.freshness import load_sync  # noqa: E402

TIERS_FILE = ROOT / "reference-library" / "multipliers" / "vendor_tiers.json"
SPECIAL_NETS_FILE = ROOT / "reference-library" / "multipliers" / "hager_special_nets.json"
STOCK_LIST_DIR = ROOT / "reference-library" / "hardware_sets"

_special_nets: dict[str, dict[str, Any]] | None = None
_special_nets_meta: dict[str, Any] | None = None

MAX_LIMIT = 25


def _clamp(limit: Any, default: int = 8) -> int:
    try:
        return max(1, min(int(limit), MAX_LIMIT))
    except (TypeError, ValueError):
        return default


def _unavailable(exc: Exception) -> dict[str, Any]:
    return {
        "error": str(exc),
        "note": (
            "The page index is not readable from this run. Price these lines "
            "manually rather than guessing - do not substitute a similar part."
        ),
    }


# ── navigation: which page, never what price ───────────────────────────────


def list_catalogs(vendor: str | None = None) -> dict[str, Any]:
    """Indexed catalogs, with age and whether their prices are list or net."""
    from datetime import date

    try:
        rows = reader.list_catalogs(vendor)
    except Exception as exc:
        return _unavailable(exc)

    catalogs = []
    stale_days = load_sync().catalog_stale_days
    for row in rows:
        effective = row.get("effectiveDate")
        age = None
        if effective:
            try:
                age = (date.today() - date.fromisoformat(effective)).days
            except (ValueError, TypeError):
                age = None
        catalogs.append(
            {
                "catalog_id": row["_id"],
                "vendor": row.get("vendor"),
                "file": row.get("fileName"),
                "kind": row.get("kind"),
                "price_basis": row.get("priceBasis"),
                "pages": row.get("pageCount", 0),
                "effective_date": effective,
                "age_days": age,
                "stale": age is not None and age > stale_days,
                "undated": effective is None,
            }
        )
    return {
        "count": len(catalogs),
        "pages": sum(c["pages"] for c in catalogs),
        "stale": sum(1 for c in catalogs if c["stale"]),
        "catalogs": catalogs,
        "note": (
            "NFR-10 is open - no named owner or refresh cadence for these sheets; "
            "age is the only staleness signal."
        ),
    }


def _document(catalog_id: str):
    row = reader.get_catalog(catalog_id)
    return page_models.PageIndexDocument.from_mongo(row) if row else None


def get_catalog_overview(catalog_id: str) -> dict[str, Any]:
    """What this catalog is, before going looking for a page in it."""
    try:
        document = _document(catalog_id)
    except Exception as exc:
        return _unavailable(exc)
    if document is None:
        return {"found": False, "catalog_id": catalog_id, "note": "no such catalog"}
    overview = document.overview
    return {
        "found": True,
        "catalog_id": document.catalog_id,
        "vendor": document.vendor,
        "file": document.file_name,
        "kind": document.kind,
        "price_basis": document.price_basis,
        "price_basis_note": price_basis_of.describe(document.price_basis),
        "effective_date": document.effective_date,
        "page_count": document.page_count,
        "summary": overview.summary,
        "product_lines": overview.product_lines,
        "how_prices_are_shown": overview.how_prices_are_shown,
        "gotchas": overview.gotchas,
        "how_to_find_a_part": overview.how_to_find_a_part,
    }


def _rank_uncached(query: str, vendor: str | None, limit: int) -> dict[str, Any]:
    documents = [
        page_models.PageIndexDocument.from_mongo(row)
        for row in reader.all_catalogs(vendor)
    ]
    return page_query.rank_pages(documents, query, limit=limit)


@lru_cache(maxsize=256)
def _rank_cached(
    query_norm: str, vendor_key: str, limit: int, watermark: str
) -> dict[str, Any]:
    vendor = vendor_key or None
    return _rank_uncached(query_norm, vendor, limit)


def clear_find_pages_cache() -> None:
    _rank_cached.cache_clear()


def find_pages(query: str, vendor: str | None = None, limit: int = 8) -> dict[str, Any]:
    """Pages worth opening. Read the price off the page, not out of this."""
    if not str(query or "").strip():
        return {"error": "query is required", "count": 0, "pages": []}
    try:
        headers = reader.list_catalogs(vendor)
        if not vendor and len(headers) > 10:
            return {
                "query": query,
                "count": 0,
                "pages": [],
                "note": (
                    "Too many catalogs to search without a vendor filter. "
                    "Pass vendor= to narrow the search."
                ),
            }
        watermark = page_query.headers_watermark(headers)
        ranked = _rank_cached(
            str(query).strip().lower(),
            str(vendor or "").strip().lower(),
            _clamp(limit),
            watermark,
        )
        return copy.deepcopy(ranked)
    except Exception as exc:
        return _unavailable(exc)


def get_page(catalog_id: str, pdf_page: int) -> dict[str, Any]:
    """One page's entry, for confirming a citation."""
    try:
        document = _document(catalog_id)
    except Exception as exc:
        return _unavailable(exc)
    if document is None:
        return {"found": False, "note": "no such catalog"}
    for page in document.pages:
        if page.pdf_page == int(pdf_page):
            return {
                "found": True,
                "catalog_id": document.catalog_id,
                "file": document.file_name,
                "file_path": f"{page_query.PRICEBOOK_DIR}/{document.file_name}",
                "pdf_page": page.pdf_page,
                "printed_page": page.printed_page,
                "locator": page.locator(),
                "title": page.title,
                "description": page.description,
                "code_prefixes": page.code_prefixes,
                "keywords": page.keywords,
                "has_prices": page.has_prices,
                "kind": page.kind,
                "confidence": page.confidence,
                "price_basis": document.price_basis,
                "effective_date": document.effective_date,
            }
    return {"found": False, "note": f"{catalog_id} has no page {pdf_page}"}


# ── curated reference data: never extracted, unchanged ─────────────────────


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
        if needle not in names:
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


HANDLERS = {
    "list_catalogs": list_catalogs,
    "get_catalog_overview": get_catalog_overview,
    "find_pages": find_pages,
    "get_page": get_page,
    "get_multiplier": get_multiplier,
    "get_special_net": get_special_net,
    "is_stock_item": is_stock_item,
}

# Guardrail: this server reads. It holds a credential that cannot write, and it
# exposes no tool that claims to.
_FORBIDDEN = ("write", "update", "insert", "upsert", "delete", "create", "set_")
assert not [t for t in TOOLS if any(word in t["name"].lower() for word in _FORBIDDEN)], (
    "catalog must expose no write tools"
)
assert set(HANDLERS) == {t["name"] for t in TOOLS}, "every tool needs a handler"


def _demo() -> None:
    """Runnable check against the real index."""
    catalogs = list_catalogs()
    if "error" in catalogs:
        print(f"catalog demo SKIPPED - {catalogs['error'][:80]}")
        return

    assert catalogs["count"] > 0, "no catalogs indexed - run `python -m cbc.pageindex.build --all`"

    hit = find_pages("3400 lock", vendor="hager", limit=3)
    assert hit["count"] >= 1, hit
    top = hit["pages"][0]
    # The pair NFR-3 needs: what pdf-tools takes, and what the page prints.
    assert top["pdf_page"] >= 1 and top["locator"], top
    assert top["why"], "a hit must say why it matched"
    # And nothing here quotes a price.
    assert "price" not in top or top.get("price") is None

    miss = find_pages("definitely-not-a-real-part-xyz")
    assert miss["count"] == 0 and "MANUAL cut-off" in miss["note"]

    assert get_multiplier("acme")["multiplier"] is None
    print(
        f"catalog demo OK - {catalogs['count']} catalogs, {catalogs['pages']} pages, "
        f"{catalogs['stale']} stale"
    )


if __name__ == "__main__":
    if "--demo" in sys.argv:
        _demo()
    else:
        serve("catalog", TOOLS, HANDLERS)
