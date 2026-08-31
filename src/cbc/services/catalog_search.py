"""Product search for the API, over the index and the hand-added parts.

Two sources, one result list:

  * **Indexed products** come from the vendor PDFs. They are regenerated on every
    reindex, so they are read-only - an edit would be silently overwritten the next
    time the vendor issues a sheet.
  * **User-created products** are the estimator's own, in MongoDB, and stay editable.
    They survive a catalog being replaced or deleted, because they were never part
    of it.

The API opens the index read-only; the worker is its only writer.
"""
from __future__ import annotations

import asyncio
import re
import sqlite3
from typing import Any

from cbc.db import db, serialise
from cbc.catalog import basis
from cbc.catalog import db as index_db
from cbc.catalog import search as index_search

_connection: sqlite3.Connection | None = None


def index_available() -> bool:
    return index_db.index_path().exists()


def _reader() -> sqlite3.Connection | None:
    """A cached read-only connection, or None when the index has not been built.

    `check_same_thread=False` is safe here precisely because it is read-only: this
    connection never writes, so there is no transaction for two threads to
    interleave. Reads run in a worker thread to keep SQLite off the event loop.
    """
    global _connection
    if _connection is None:
        if not index_available():
            return None
        path = index_db.index_path()
        _connection = index_db.connect(path, readonly=True)
        _connection.execute("PRAGMA query_only=1")
    return _connection


def _search_sync(**kwargs: Any) -> dict[str, Any]:
    connection = _reader()
    if connection is None:
        return {"count": 0, "total_matched": 0, "results": []}
    return index_search.search(connection, **kwargs)


async def search_index(
    query: str,
    *,
    vendor: str | None = None,
    category: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Indexed products, shaped the way the catalog screen expects them."""
    if not query:
        return []
    found = await asyncio.to_thread(
        _search_sync, query=query, vendor=vendor, category=category, limit=limit
    )
    for row in found["results"]:
        row["price_basis"] = basis.price_basis(row["source_file"], row["vendor"])
    return [
        {
            "id": f"idx:{row['product_id']}",
            "part": row["product_code"],
            "description": row["product_name"] or "",
            "manufacturer": row["vendor"],
            "division": row["category"],
            # A sheet's prices are list or net, and the index does not record which,
            # so every indexed price used to be handed over as `listPrice` and shown
            # as "list $X". On a Hager special net that is backwards: the number is
            # already the cost. `listPrice` is now populated only when the price
            # really is a list price, so a consumer that reads it without checking
            # the basis gets nothing rather than a number that means the opposite.
            "listPrice": row["price"] if row["price_basis"] == basis.LIST else None,
            "netPrice": row["price"] if row["price_basis"] == basis.NET else None,
            "price": row["price"],
            "priceBasis": row["price_basis"],
            "priceBasisNote": basis.describe(row["price_basis"]),
            "cost": None,
            "sellAt": None,
            "unit": row["unit"],
            "priceBook": row["source_file"],
            "sourcePage": row["page_number"],
            "effective": row["effective_date"],
            "relevance": row["relevance_score"],
            # The screen uses this to decide what may be edited. A part read from a
            # vendor PDF is rewritten on the next reindex, so editing it here would
            # be a change that quietly disappears.
            "source": "catalog",
            "editable": False,
        }
        for row in found["results"]
    ]


async def search_manual(
    query: str | None,
    *,
    division: str | None = None,
    manufacturer: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """The estimator's own parts. Editable, and independent of any catalog."""
    mongo: dict[str, Any] = {"seedSource": {"$ne": "price book ingest"}}
    if division:
        mongo["division"] = division
    if manufacturer:
        mongo["manufacturer"] = manufacturer
    if query:
        needle = re.escape(query)  # user input, not a pattern
        mongo["$or"] = [
            {"part": {"$regex": f"^{needle}", "$options": "i"}},
            {"description": {"$regex": needle, "$options": "i"}},
            {"manufacturer": {"$regex": needle, "$options": "i"}},
        ]
    rows = await db.products.find(mongo).sort("part", 1).to_list(limit)
    # A hand-added part keeps cost and list in separate columns the estimator filled
    # in, so there is nothing to disambiguate: its listPrice is a list price.
    return [
        {
            **serialise(row),
            "priceBasis": basis.LIST,
            "priceBasisNote": basis.describe(basis.LIST),
            "netPrice": None,
            "source": "manual",
            "editable": True,
        }
        for row in rows
    ]


async def search(
    query: str | None,
    *,
    division: str | None = None,
    manufacturer: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Both sources, the estimator's own parts first.

    Their own entries rank above the catalog deliberately: a part somebody typed in
    is one they could not find, or one they corrected, and burying it under 20 000
    indexed rows would send them to type it again.
    """
    manual, indexed = await asyncio.gather(
        search_manual(query, division=division, manufacturer=manufacturer, limit=limit),
        search_index(query or "", vendor=manufacturer, category=division, limit=limit),
    )
    combined = (manual + indexed)[:limit]
    return {
        "products": combined,
        "total": len(manual) + len(indexed),
        "counts": {"manual": len(manual), "catalog": len(indexed)},
        "indexAvailable": index_available(),
        "note": (
            None
            if index_available()
            else "The catalog index has not been built yet, so only hand-added parts "
                 "are searchable. Build it with `python -m cbc.catalog.rebuild`."
        ),
    }
