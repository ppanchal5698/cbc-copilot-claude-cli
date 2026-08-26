#!/usr/bin/env python3
"""pricebook MCP server - search vendor price books and resolve net cost.

Cost path 2 of three (.claude/memory/cost_sourcing_rules.md):
    cost = manufacturer list price x CBC multiplier tier

Fuzzy matching uses stdlib difflib rather than rapidfuzz - one less dependency for
a job that is mostly exact part-number containment anyway.

READ-ONLY: this server never writes to pricebooks/ (.claude/rules/file-safety.md).
"""
from __future__ import annotations

import difflib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _runtime import serve  # noqa: E402
from tools import TOOLS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PRICEBOOK_DIR = Path(os.environ.get("PRICEBOOK_DIR") or ROOT / "pricebooks")
INDEX_FILE = PRICEBOOK_DIR / "index.json"
TIERS_FILE = ROOT / "reference-library" / "multipliers" / "vendor_tiers.json"

PRICE_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{3})*\.\d{2})(?![\d])")
MIN_RATIO = 0.55
MAX_MATCHES = 25

# ponytail: page text is cached in-process only. A 744-page book takes a few seconds
# on first touch and is then free for the life of the server. Add an on-disk cache
# only if cold-start latency in the headless pipeline actually becomes a problem -
# it must not live under pricebooks/, which is read-only during a run.
_PAGE_CACHE: dict[str, list[str]] = {}


def _catalog() -> dict[str, Any]:
    if not INDEX_FILE.exists():
        return {"pricebooks": []}
    return json.loads(INDEX_FILE.read_text(encoding="utf-8"))


def _entries(vendor: str | None = None, division: str | None = None) -> list[dict[str, Any]]:
    books = _catalog().get("pricebooks", [])
    if vendor:
        needle = vendor.strip().lower()
        books = [b for b in books if needle in b.get("vendor", "").lower()]
    if division:
        books = [b for b in books if division in (b.get("divisions") or [division])]
    return books


def _pages(entry: dict[str, Any]) -> list[str]:
    """Return per-page text for one price book, cached in process."""
    path = PRICEBOOK_DIR / entry["file"]
    key = str(path)
    if key in _PAGE_CACHE:
        return _PAGE_CACHE[key]
    if not path.exists() or path.suffix.lower() != ".pdf":
        _PAGE_CACHE[key] = []
        return []
    doc = fitz.open(path)
    try:
        _PAGE_CACHE[key] = [page.get_text() for page in doc]
    finally:
        doc.close()
    return _PAGE_CACHE[key]


def list_vendors() -> dict[str, Any]:
    books = _catalog().get("pricebooks", [])
    tiers = json.loads(TIERS_FILE.read_text(encoding="utf-8")) if TIERS_FILE.exists() else {}
    by_vendor = {v.get("key", v.get("name", "")).lower(): v for v in tiers.get("vendors", [])}
    out = []
    for book in books:
        tier = by_vendor.get(book.get("vendor", "").lower(), {})
        out.append(
            {
                "vendor": book.get("vendor"),
                "name": book.get("name"),
                "file": book.get("file"),
                "effective_date": book.get("effective_date"),
                "kind": book.get("kind"),
                "multiplier": tier.get("multiplier"),
                "multiplier_note": tier.get("note"),
            }
        )
    return {
        "pricebook_dir": str(PRICEBOOK_DIR),
        "count": len(out),
        "pricebooks": out,
    }


def _score(query: str, line: str) -> float:
    lowered = line.lower()
    if query in lowered:
        return 1.0
    return difflib.SequenceMatcher(None, query, lowered).ratio()


def search_product(
    query: str,
    vendor: str | None = None,
    division: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    needle = query.strip().lower()
    hits: list[dict[str, Any]] = []
    searched: list[str] = []

    for entry in _entries(vendor, division):
        pages = _pages(entry)
        if not pages:
            continue
        searched.append(entry["file"])
        for page_number, text in enumerate(pages, start=1):
            for line in text.splitlines():
                stripped = line.strip()
                if len(stripped) < 3:
                    continue
                score = _score(needle, stripped)
                if score >= MIN_RATIO:
                    hits.append(
                        {
                            "vendor": entry.get("vendor"),
                            "source_file": entry["file"],
                            "source_page": page_number,
                            "effective_date": entry.get("effective_date"),
                            "line": stripped[:200],
                            "score": round(score, 3),
                        }
                    )

    hits.sort(key=lambda h: (-h["score"], h["source_page"]))
    return {
        "query": query,
        "vendor_filter": vendor,
        "books_searched": searched,
        "hit_count": len(hits),
        "hits": hits[:limit],
        "note": "No hits does not mean no product - it may be a MANUAL cut-off item."
        if not hits
        else None,
    }


def get_multiplier(vendor: str, tier: str | None = None) -> dict[str, Any]:
    if not TIERS_FILE.exists():
        return {"vendor": vendor, "multiplier": None, "note": "vendor_tiers.json not found"}
    data = json.loads(TIERS_FILE.read_text(encoding="utf-8"))
    needle = vendor.strip().lower()
    for record in data.get("vendors", []):
        names = {str(record.get("key", "")).lower(), str(record.get("name", "")).lower()}
        if needle not in names and needle not in str(record.get("name", "")).lower():
            continue
        categories = record.get("categories") or {}
        if tier and categories:
            key = tier.strip().lower().replace(" ", "_")
            if key in categories:
                return {
                    "vendor": record.get("name"),
                    "tier": key,
                    "multiplier": categories[key],
                    "effective_date": record.get("effective_date"),
                    "account": record.get("account"),
                    "source": record.get("source"),
                }
            return {
                "vendor": record.get("name"),
                "tier": tier,
                "multiplier": None,
                "available_categories": sorted(categories),
                "note": "Unknown category for this vendor - do not guess, ask the estimator.",
            }
        return {
            "vendor": record.get("name"),
            "tier": record.get("tier"),
            "multiplier": record.get("multiplier"),
            "categories": categories or None,
            "effective_date": record.get("effective_date"),
            "account": record.get("account"),
            "note": record.get("note"),
            "source": record.get("source"),
        }
    return {
        "vendor": vendor,
        "multiplier": None,
        "note": "Vendor not in the tier sheet. Price manually (MANUAL cut-off) - never guess.",
    }


def lookup_pricing(part_number: str, vendor: str, category: str | None = None) -> dict[str, Any]:
    needle = part_number.strip().lower()
    matches: list[dict[str, Any]] = []

    for entry in _entries(vendor):
        for page_number, text in enumerate(_pages(entry), start=1):
            if len(matches) >= MAX_MATCHES:
                break
            lines = text.splitlines()
            for index, line in enumerate(lines):
                if needle not in line.lower():
                    continue
                window = " ".join(lines[index : index + 6])
                prices = [float(p.replace(",", "")) for p in PRICE_RE.findall(window)]
                matches.append(
                    {
                        "vendor": entry.get("vendor"),
                        "source_file": entry["file"],
                        "source_page": page_number,
                        "effective_date": entry.get("effective_date"),
                        "context": window[:300],
                        "list_price_candidates": prices[:8],
                    }
                )
                if len(matches) >= MAX_MATCHES:
                    break

    tier = get_multiplier(vendor, category)
    multiplier = tier.get("multiplier")
    net_cost = None
    single = None
    if len(matches) == 1 and len(matches[0]["list_price_candidates"]) == 1:
        single = matches[0]["list_price_candidates"][0]
        if isinstance(multiplier, (int, float)):
            net_cost = round(single * float(multiplier), 2)

    return {
        "part_number": part_number,
        "vendor": vendor,
        "match_count": len(matches),
        "matches": matches,
        "multiplier": multiplier,
        "multiplier_tier": tier.get("tier"),
        "multiplier_effective_date": tier.get("effective_date"),
        "list_price": single,
        "net_cost": net_cost,
        "cost_source": "LIST_X_MULTIPLIER" if net_cost is not None else "MANUAL",
        "note": (
            "Unambiguous single match priced at list x multiplier."
            if net_cost is not None
            else "Ambiguous or missing - the estimator prices this line. Adders "
            "(electrification, NRP, premium finish) are never included here."
        ),
    }


HANDLERS = {
    "list_vendors": list_vendors,
    "search_product": search_product,
    "lookup_pricing": lookup_pricing,
    "get_multiplier": get_multiplier,
}


if __name__ == "__main__":
    serve("pricebook", TOOLS, HANDLERS)
