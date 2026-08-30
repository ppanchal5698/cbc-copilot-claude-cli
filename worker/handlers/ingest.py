"""Job-type handlers invoked after a Claude pass completes."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId

from api.db import db

REPO_ROOT = Path(__file__).resolve().parents[2]


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def ingest_pricebook(job: dict) -> str:
    """Load the parts Claude read off a price book into the catalog."""
    payload = job.get("payload") or {}
    output_path = (REPO_ROOT / payload.get("outputPath", ".cache/pricebook-ingest.json")).resolve()
    # This function reads and then deletes whatever it is pointed at, so it does
    # not take the path on trust even though the worker now sets it.
    if not output_path.is_relative_to(REPO_ROOT / ".cache"):
        raise ValueError(f"ingest output must stay under .cache/: {output_path}")
    if not output_path.exists():
        return "no ingest file produced"

    data = json.loads(output_path.read_text(encoding="utf-8"))
    book_id = ObjectId(payload["priceBookId"])
    written = 0
    for product in data.get("products", []):
        if not product.get("part"):
            continue
        # Keyed on the vendor as well as the part: a part number is only unique
        # within its manufacturer, and keying on `part` alone made Rockwood's
        # sheet overwrite Hager's costs for every number they happen to share.
        manufacturer = product.get("manufacturer")
        await db.products.update_one(
            {"part": product["part"], "manufacturer": manufacturer},
            {
                "$set": {
                    "description": product.get("description", ""),
                    "division": product.get("division"),
                    "listPrice": product.get("list_price"),
                    "multiplier": product.get("multiplier"),
                    "cost": product.get("cost"),
                    "priceBookId": book_id,
                    "sourcePage": product.get("source_page"),
                    "seedSource": "price book ingest",
                    "updatedAt": _now(),
                    "updatedBy": "claude",
                },
                "$setOnInsert": {
                    "part": product["part"],
                    "manufacturer": manufacturer,
                    "createdAt": _now(),
                },
            },
            upsert=True,
        )
        written += 1

    # An effective date is only written when the ingest actually read one. Setting
    # it unconditionally wrote null over a date purchasing had entered by hand,
    # and an undated book reports `stale: false` - so a lapsed sheet quietly
    # stopped being flagged, which is the whole point of the price-books screen.
    changes: dict = {"partCount": written, "lastIngestedAt": _now()}
    if data.get("effective_date"):
        changes["effective"] = data["effective_date"]
    await db.price_books.update_one({"_id": book_id}, {"$set": changes})
    output_path.unlink(missing_ok=True)
    return f"{written} parts written to the catalog"
