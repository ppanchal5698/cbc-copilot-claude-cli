#!/usr/bin/env python3
"""catalog MCP server - live product and multiplier data from MongoDB.

READ-ONLY by design, like p21-connector. The estimator maintains the catalog in
the Ops-Hub UI and the ingest job writes parts from price books; a pricing pass
only reads. That is what makes "Claude is aware of the newest data" true rather
than aspirational - there is no snapshot to go stale.

Uses pymongo (sync) because the MCP handlers here are synchronous.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _runtime import serve  # noqa: E402
from tools import TOOLS  # noqa: E402

URI = os.environ.get(
    "MONGODB_URI", "mongodb://cbc:cbc_local_dev@localhost:27017/cbc_opshub?authSource=admin"
)
DB_NAME = os.environ.get("MONGODB_DB", "cbc_opshub")
STALE_DAYS = 180

_client: MongoClient | None = None


def _db():
    global _client
    if _client is None:
        _client = MongoClient(URI, serverSelectionTimeoutMS=5000)
    return _client[DB_NAME]


def _clean(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not document:
        return None
    return {
        ("id" if k == "_id" else k): (str(v) if k.endswith("Id") or k == "_id" else v)
        for k, v in document.items()
    }


def _age_days(effective: str | None) -> int | None:
    if not effective:
        return None
    try:
        return (date.today() - date.fromisoformat(effective)).days
    except (ValueError, TypeError):
        return None


def _with_book(product: dict[str, Any]) -> dict[str, Any]:
    book = None
    if product.get("priceBookId"):
        book = _db().priceBooks.find_one({"_id": product["priceBookId"]})
    cleaned = _clean(product) or {}
    if book:
        cleaned["priceBook"] = {
            "vendor": book.get("vendor"),
            "program": book.get("program"),
            "multiplier": book.get("multiplier"),
            "effective": book.get("effective"),
            "ageDays": _age_days(book.get("effective")),
            "stale": (_age_days(book.get("effective")) or 0) > STALE_DAYS,
        }
    return cleaned


def search_products(
    query: str,
    division: str | None = None,
    manufacturer: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    needle = query.strip()
    mongo_query: dict[str, Any] = {
        "$or": [
            {"part": {"$regex": f"^{needle}", "$options": "i"}},
            {"part": {"$regex": needle, "$options": "i"}},
            {"description": {"$regex": needle, "$options": "i"}},
            {"manufacturer": {"$regex": needle, "$options": "i"}},
        ]
    }
    if division:
        mongo_query["division"] = division
    if manufacturer:
        mongo_query["manufacturer"] = {"$regex": manufacturer, "$options": "i"}

    found = list(_db().products.find(mongo_query).limit(min(int(limit), 100)))
    # Exact part-number matches first - an estimator typing a part wants that part.
    found.sort(key=lambda p: (str(p.get("part", "")).lower() != needle.lower(), p.get("part", "")))

    return {
        "query": query,
        "count": len(found),
        "products": [_with_book(p) for p in found],
        "note": (
            "No catalog match. This may be a MANUAL cut-off item - do not "
            "substitute the nearest stock part."
            if not found
            else None
        ),
    }


def get_product(part: str) -> dict[str, Any]:
    product = _db().products.find_one({"part": part})
    if not product:
        return {
            "part": part,
            "found": False,
            "note": "Not in the catalog. Price manually or check the source price book.",
        }
    return {"part": part, "found": True, "product": _with_book(product)}


def get_multiplier(vendor: str, category: str | None = None) -> dict[str, Any]:
    needle = vendor.strip()
    book = _db().priceBooks.find_one(
        {
            "$or": [
                {"vendor": {"$regex": f"^{needle}$", "$options": "i"}},
                {"displayName": {"$regex": needle, "$options": "i"}},
            ],
            "multiplier": {"$ne": None},
        }
    )
    if not book:
        return {
            "vendor": vendor,
            "multiplier": None,
            "note": "No multiplier tier on file. Price manually - never guess.",
        }

    categories = book.get("categories") or {}
    if category:
        key = category.strip().lower().replace(" ", "_").replace("-", "_")
        if key in categories:
            return {
                "vendor": book.get("vendor"),
                "category": key,
                "multiplier": categories[key],
                "effective": book.get("effective"),
                "lastReviewed": book.get("lastReviewed"),
                "account": book.get("account"),
                "ageDays": _age_days(book.get("effective")),
            }
        if categories:
            return {
                "vendor": book.get("vendor"),
                "category": category,
                "multiplier": None,
                "availableCategories": sorted(categories),
                "note": "Unknown category for this vendor - ask the estimator.",
            }

    return {
        "vendor": book.get("vendor"),
        "multiplier": book.get("multiplier"),
        "categories": categories or None,
        "effective": book.get("effective"),
        "lastReviewed": book.get("lastReviewed"),
        "steward": book.get("steward"),
        "account": book.get("account"),
        "ageDays": _age_days(book.get("effective")),
        "stale": (_age_days(book.get("effective")) or 0) > STALE_DAYS,
        "note": book.get("note"),
    }


def list_price_books(vendor: str | None = None) -> dict[str, Any]:
    query = {"vendor": {"$regex": vendor, "$options": "i"}} if vendor else {}
    books = list(_db().priceBooks.find(query).sort("vendor", 1))

    out = []
    for book in books:
        age = _age_days(book.get("effective"))
        out.append(
            {
                "vendor": book.get("vendor"),
                "program": book.get("program"),
                "multiplier": book.get("multiplier"),
                "effective": book.get("effective"),
                "lastReviewed": book.get("lastReviewed"),
                "steward": book.get("steward"),
                "partCount": book.get("partCount", 0),
                "ageDays": age,
                "stale": age is not None and age > STALE_DAYS,
                "undated": book.get("effective") is None,
            }
        )

    return {
        "count": len(out),
        "priceBooks": out,
        "stale": sum(1 for b in out if b["stale"]),
        "undated": sum(1 for b in out if b["undated"]),
        "stewardship": "NFR-10 is open - no named owner or refresh cadence. Age is the only signal.",
    }


HANDLERS = {
    "search_products": search_products,
    "get_product": get_product,
    "get_multiplier": get_multiplier,
    "list_price_books": list_price_books,
}

# Guardrail: this server reads. Nothing here may ever write to the catalog.
_FORBIDDEN = ("write", "update", "insert", "upsert", "delete", "create", "set_")
assert not [t for t in TOOLS if any(word in t["name"].lower() for word in _FORBIDDEN)], (
    "catalog must expose no write tools"
)


def _demo() -> None:
    """Runnable check against the seeded database."""
    books = list_price_books()
    assert books["count"] > 0, "no price books - run scripts/seed_db.py"

    hager = get_multiplier("hager", "locks")
    assert hager["multiplier"] == 0.29, hager

    unknown = get_multiplier("acme")
    assert unknown["multiplier"] is None and "never guess" in unknown["note"]

    hit = search_products("150CX18")
    assert hit["count"] >= 1, hit
    assert hit["products"][0]["part"].startswith("150CX18")

    miss = search_products("definitely-not-a-real-part-xyz")
    assert miss["count"] == 0 and "MANUAL" in miss["note"]

    print(f"catalog demo OK - {books['count']} price books, {books['stale']} stale")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        _demo()
    else:
        serve("catalog", TOOLS, HANDLERS)
