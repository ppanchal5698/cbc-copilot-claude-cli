#!/usr/bin/env python3
"""Find products that share a (manufacturer, part) key, so the unique index can build.

`products` was unique on `part` alone, which meant the price-book ingest upserted
one vendor's row over another's whenever they shared a part number. The index is
now (manufacturer, part); on a database that already collapsed rows there may be
leftovers it cannot build over.

    python scripts/dedupe_products.py            # report only
    python scripts/dedupe_products.py --apply    # keep the newest, delete the rest
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo import MongoClient  # noqa: E402

from api.config import settings  # noqa: E402


def main() -> int:
    apply = "--apply" in sys.argv
    client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
    products = client[settings.mongodb_db]["products"]

    groups = list(
        products.aggregate(
            [
                {
                    "$group": {
                        "_id": {"manufacturer": "$manufacturer", "part": "$part"},
                        "ids": {"$push": "$_id"},
                        "n": {"$sum": 1},
                    }
                },
                {"$match": {"n": {"$gt": 1}}},
                {"$sort": {"n": -1}},
            ]
        )
    )

    if not groups:
        print("No duplicates. The (manufacturer, part) index can build.")
        return 0

    removable = sum(group["n"] - 1 for group in groups)
    print(f"{len(groups)} duplicated key(s), {removable} row(s) beyond the first:\n")
    for group in groups[:50]:
        key = group["_id"]
        print(f"  {key.get('manufacturer') or '(no manufacturer)':<24} {key.get('part')}  x{group['n']}")
    if len(groups) > 50:
        print(f"  ... and {len(groups) - 50} more")

    if not apply:
        print("\nReport only. Re-run with --apply to keep the most recently updated "
              "row in each group and delete the rest.")
        return 1

    deleted = 0
    for group in groups:
        rows = list(
            products.find({"_id": {"$in": group["ids"]}}).sort([("updatedAt", -1), ("_id", -1)])
        )
        for stale in rows[1:]:
            products.delete_one({"_id": stale["_id"]})
            deleted += 1
    print(f"\nDeleted {deleted} row(s). Restart the API to build the index.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
