#!/usr/bin/env python3
"""pricebook MCP server - net cost from the vendor price books.

Cost path 2 of three (.claude/memory/cost_sourcing_rules.md):
    cost = manufacturer list price x CBC multiplier tier

This server used to answer every question by opening each price book and running
difflib over every line of every page: 6.02 s on a cold process, 2.51 s warm, and
a fresh MCP subprocess per run meant it was paid again every time - minutes of wall
clock on a pricing pass that looks up fifty parts.

It now reads the same SQLite FTS5 index the catalog server reads, built once in the
background when a catalog is uploaded. The PDFs are still the source of truth; the
index is derived from them and is rebuilt with `python -m catalog_index.rebuild`.

READ-ONLY: this server never writes to pricebooks/ (.claude/rules/file-safety.md),
and its database connection is opened `query_only` so that is enforced rather than
promised.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mcp-servers"))

from _runtime import load_server, serve  # noqa: E402
from tools import TOOLS  # noqa: E402  - this server's own tools.py

# One implementation of catalog search, exposed under both server names because the
# agents and skills refer to each of them by name.
#
# Loaded through `load_server` rather than by putting the catalog directory on
# sys.path: both servers have a `tools.py`, and adding that directory made
# `from tools import TOOLS` above resolve to the wrong one - which is precisely the
# collision load_server was written to prevent. Import order matters here.
_catalog = load_server("catalog")

list_vendors = _catalog.list_vendors
get_multiplier = _catalog.get_multiplier
lookup_pricing = _catalog.lookup_pricing
get_special_net = _catalog.get_special_net
is_stock_item = _catalog.is_stock_item


def search_product(
    query: str,
    vendor: str | None = None,
    division: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search the indexed price books. Returns ranked hits with source_page."""
    return _catalog.search_product(query, vendor=vendor, division=division, limit=limit)


HANDLERS = {
    "list_vendors": list_vendors,
    "search_product": search_product,
    "lookup_pricing": lookup_pricing,
    "get_multiplier": get_multiplier,
}


def _demo() -> None:
    """Runnable check against the real index."""
    catalog = list_vendors()
    assert catalog["count"] > 0, "no vendors indexed - run `python -m catalog_index.rebuild`"

    hit = search_product("B-2888", vendor="bobrick")
    assert hit["hit_count"] >= 1, hit
    assert hit["hits"][0]["source_page"], "every hit carries its page (NFR-3)"

    miss = search_product("definitely-not-a-real-part-xyz")
    assert miss["hit_count"] == 0

    unknown = get_multiplier("acme")
    assert unknown["multiplier"] is None and "never guess" in unknown["note"]
    print(f"pricebook demo OK - {catalog['count']} vendors indexed")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        _demo()
    else:
        serve("pricebook", TOOLS, HANDLERS)
