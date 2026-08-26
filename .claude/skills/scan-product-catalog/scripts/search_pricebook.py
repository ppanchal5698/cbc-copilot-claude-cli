#!/usr/bin/env python3
"""CLI wrapper over the pricebook MCP server, for use outside an MCP session.

    python search_pricebook.py --list
    python search_pricebook.py hager 3510 --category locks
    python search_pricebook.py hager "storeroom lock" --search
    python search_pricebook.py --demo

Fuzzy matching is stdlib difflib (inside the server) - no rapidfuzz needed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "mcp-servers"))

from _runtime import load_server  # noqa: E402

pricebook = load_server("pricebook")


def _demo() -> None:
    """Runnable check against the real price books."""
    catalog = pricebook.list_vendors()
    assert catalog["count"] > 0, "no price books indexed - check pricebooks/index.json"

    tier = pricebook.get_multiplier("hager", "locks")
    assert tier["multiplier"] == 0.29, tier
    assert tier["effective_date"] == "2026-03-02", tier

    unknown = pricebook.get_multiplier("acme")
    assert unknown["multiplier"] is None and "never guess" in unknown["note"]

    bad_category = pricebook.get_multiplier("hager", "unicorns")
    assert bad_category["multiplier"] is None, bad_category

    # A worked cost: list x multiplier, the way Path 2 computes it.
    assert round(256.31 * tier["multiplier"], 2) == 74.33
    print(f"search_pricebook demo OK - {catalog['count']} books indexed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vendor", nargs="?", help="Vendor key, e.g. hager")
    parser.add_argument("query", nargs="?", help="Part number or keywords")
    parser.add_argument("--category", help="Multiplier category, e.g. locks")
    parser.add_argument("--search", action="store_true", help="Keyword search instead of lookup")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--list", action="store_true", help="List indexed price books")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    if args.demo:
        _demo()
        return 0
    if args.list or not args.vendor:
        print(json.dumps(pricebook.list_vendors(), indent=2))
        return 0
    if not args.query:
        print(json.dumps(pricebook.get_multiplier(args.vendor, args.category), indent=2))
        return 0

    if args.search:
        result = pricebook.search_product(args.query, vendor=args.vendor, limit=args.limit)
    else:
        result = pricebook.lookup_pricing(args.query, args.vendor, args.category)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
