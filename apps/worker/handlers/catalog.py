"""Catalog indexing jobs.

These run on the existing queue rather than a new one, which means they inherit
everything that was built for it: atomic claim, heartbeats, a reaper for a worker
that died mid-job, exponential backoff, permanent-vs-transient failure
classification, cancellation and an audit trail. A second queue would be the same
machinery again, with its own bugs.

The worker is the **only** writer to the SQLite index. The API and the MCP servers
open it read-only, which is what keeps a single-writer database safe with several
processes reading it.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cbc.config import settings
from cbc.db import db, oid
from cbc.catalog import db as index_db
from cbc.catalog import pipeline
from cbc.catalog.pipeline import IndexingError

log = logging.getLogger("cbc.worker.catalog")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _index_sync(path: Path, vendor: str, effective_date: str | None) -> dict[str, Any]:
    """All SQLite work for one catalog, on one thread."""
    connection = index_db.initialise()
    try:
        return pipeline.index_catalog(
            connection, path, vendor=vendor, effective_date=effective_date
        )
    finally:
        connection.close()


def _delete_sync(catalog_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    connection = index_db.initialise()
    try:
        return pipeline.delete_catalog(connection, catalog_id), index_db.integrity_report(connection)
    finally:
        connection.close()


def _vendor_for(book: dict[str, Any] | None, filename: str) -> str:
    """The vendor a file belongs to, from the price-book record or its name."""
    if book and book.get("vendor"):
        return str(book["vendor"]).strip().lower()
    return filename.split("_")[0].lower() or "unknown"


async def index_catalog(job: dict[str, Any]) -> str:
    """Read one catalog file into the search index.

    Extraction is CPU-bound and takes seconds to minutes, which is exactly why it
    belongs on the queue and not on the request that uploaded the file.
    """
    payload = job.get("payload") or {}
    filename = payload.get("filename")
    if not filename:
        raise ValueError("index_catalog job has no payload.filename")

    # The filename comes from a job payload, so it is not taken on trust: it is
    # reduced to a bare name and resolved inside the price-book directory.
    from cbc.services import storage

    safe = storage.safe_name(str(filename))
    path = (settings.pricebook_dir / safe).resolve()
    if not path.is_relative_to(settings.pricebook_dir.resolve()):
        raise ValueError(f"catalog file must be inside {settings.pricebook_dir}: {filename!r}")

    book = None
    if payload.get("priceBookId"):
        book = await db.price_books.find_one({"_id": oid(payload["priceBookId"])})

    # The SQLite connection is created, used and closed inside the thread: a
    # connection cannot be shared across threads, and a 744-page book would stall
    # the heartbeat and the cancel watcher if it ran on the event loop.
    try:
        report = await asyncio.to_thread(
            _index_sync, path, _vendor_for(book, safe), (book or {}).get("effective")
        )
    except IndexingError as exc:
        if book and payload.get("priceBookId"):
            from cbc.services import storage as file_storage
            from cbc.services.document_index import enqueue_index, inventory_kind

            kind = inventory_kind(safe) or book.get("kind") or "price_book"
            await db.price_books.update_one(
                {"_id": book["_id"]},
                {"$set": {"indexStatus": "deep_index_queued", "updatedAt": _now()}},
            )
            document_id, _ = await enqueue_index(
                source_path=file_storage.relative(path),
                client_id=_vendor_for(book, safe),
                document_type=kind,
                effective_date=book.get("effective"),
                actor=job.get("createdBy") or "worker",
                trigger="catalog_failed",
                price_book_id=str(book["_id"]),
            )
            log.info(
                "catalog index failed for %s — queued deep index %s: %s",
                safe,
                document_id,
                exc,
            )
        raise

    # Mirror the outcome onto the price-book record the UI reads.
    if book:
        await db.price_books.update_one(
            {"_id": book["_id"]},
            {"$set": {
                "catalogId": report["catalog_id"],
                "indexStatus": report["status"],
                "partCount": report.get("products", 0),
                "extractor": report.get("extractor"),
                "validationRate": report.get("validation_rate"),
            }},
        )

    if report.get("skipped"):
        return f"unchanged since the last index - {report['products']} products still searchable"
    return (
        f"{report['products']} products indexed from {report['pages_read']} page(s) "
        f"via {report['extractor']} at a {report['validation_rate']:.0%} validation rate"
    )


async def delete_catalog(job: dict[str, Any]) -> str:
    """Remove a catalog from the index, and verify nothing was left behind."""
    payload = job.get("payload") or {}
    catalog_id = payload.get("catalogId")
    if not catalog_id:
        raise ValueError("delete_catalog job has no payload.catalogId")

    report, integrity = await asyncio.to_thread(_delete_sync, str(catalog_id))

    if report["orphans"] or not integrity["ok"]:
        # The whole point of the cascade is that this cannot happen. If it ever
        # does, it is a real defect and must not be reported as a clean delete.
        raise RuntimeError(
            f"catalog {catalog_id} did not delete cleanly: "
            f"{report['orphans']} orphan(s), {integrity['problems']}"
        )

    if payload.get("priceBookId"):
        await db.price_books.update_one(
            {"_id": oid(payload["priceBookId"])},
            {"$set": {"indexStatus": "deleted", "partCount": 0}},
        )
    return f"{report['removed']} product(s) removed from the index, no orphans"
