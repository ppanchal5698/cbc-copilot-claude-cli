"""Indexing one catalog file, end to end.

    classify → extract → validate → stage → activate

The order is the safety property. Nothing becomes searchable until `activate`, and
`activate` is one transaction, so a catalog is either wholly its old version or
wholly its new one. A crash, a corrupt PDF or a vendor who reformatted their sheet
all end the same way: the previous version stays live and the failure is recorded
with its reason.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from catalog_index import extractors, registry, validate

log = logging.getLogger("cbc.catalog.index")

# Below this share of rows surviving validation, assume the layout changed rather
# than that the book is genuinely mostly noise. Indexing it anyway would fill search
# with page furniture and quietly bury the real parts.
MIN_VALIDATION_RATE = 0.15
MIN_PRODUCTS = 5


class IndexingError(RuntimeError):
    """Extraction produced nothing usable. Permanent - retrying reads the same file."""


def index_catalog(
    connection: sqlite3.Connection,
    path: Path,
    *,
    vendor: str,
    effective_date: str | None = None,
    max_pages: int | None = None,
) -> dict[str, Any]:
    """Read one catalog file into the index. Returns a report."""
    if not path.exists():
        raise IndexingError(f"catalog file is missing: {path}")

    hash_hex = registry.file_hash(path)
    catalog_id, needs_indexing = registry.register(
        connection, vendor=vendor, file_name=path.name, hash_hex=hash_hex,
        effective_date=effective_date,
    )
    if not needs_indexing:
        return {"catalog_id": catalog_id, "status": "ready", "skipped": "unchanged",
                "products": registry.status_of(connection, catalog_id)["product_count"]}

    # A previous attempt may have died part-way through; its rows are invisible but
    # they are still taking up space.
    registry.clear_stale_staging(connection, catalog_id)
    registry.set_status(connection, catalog_id, "processing")

    try:
        extract = extractors.choose(path)
        kwargs = {} if extract is extractors.extract_spreadsheet else {"max_pages": max_pages}
        result = extract(path, vendor, **kwargs)
    except Exception as exc:
        registry.set_status(connection, catalog_id, "failed", f"extraction failed: {exc}")
        raise IndexingError(f"could not read {path.name}: {exc}") from exc

    kept, rejected = validate.clean(result.records)
    result.rejected.update(rejected)
    considered = len(kept) + sum(result.rejected.values())
    rate = 1.0 if considered == 0 else len(kept) / considered

    if len(kept) < MIN_PRODUCTS or rate < MIN_VALIDATION_RATE:
        reason = (
            f"{len(kept)} usable product(s) from {result.pages_read} page(s) "
            f"at a {rate:.0%} validation rate - below the threshold, so this is "
            f"treated as an unreadable layout rather than indexed as noise. "
            f"Rejections: {result.rejected or 'none'}"
        )
        registry.set_status(connection, catalog_id, "failed", reason)
        raise IndexingError(reason)

    registry.set_status(connection, catalog_id, "indexing")
    current = registry.status_of(connection, catalog_id) or {}
    build_id, staged = registry.stage(
        connection, catalog_id, kept, version=int(current.get("version", 0)) + 1
    )
    try:
        live = registry.activate(connection, catalog_id, build_id, extractor=result.extractor)
    except Exception as exc:
        registry.discard_build(connection, build_id)
        registry.set_status(connection, catalog_id, "failed", f"activation failed: {exc}")
        raise

    log.info(
        "indexed %s (%s): %s products from %s pages, %.0f%% validation rate",
        path.name, vendor, live, result.pages_read, rate * 100,
    )
    return {
        "catalog_id": catalog_id,
        "status": "ready",
        "products": live,
        "staged": staged,
        "pages_read": result.pages_read,
        "extractor": result.extractor,
        "validation_rate": round(rate, 3),
        "rejected": result.rejected,
    }


def delete_catalog(connection: sqlite3.Connection, catalog_id: str) -> dict[str, Any]:
    """Remove a catalog from the index, and prove nothing was left behind."""
    registry.set_status(connection, catalog_id, "deleting")
    return registry.delete(connection, catalog_id)
