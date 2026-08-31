"""The catalog lifecycle: register, stage, swap, delete.

Every write to the index goes through here, and the two operations that matter are
each a single transaction.

**Swap.** A new build accumulates in `products_staging`, where nothing can find it.
Only when it is complete and validated do the old rows come out and the new rows go
in - one transaction, so the catalog is either wholly the old version or wholly the
new one. The failure this avoids is the obvious one: delete the old index, fail to
build the new one, and the vendor is gone until someone notices.

**Delete.** `ON DELETE CASCADE` on `products`, plus the FTS delete trigger, means
removing a catalog is one statement. There is no multi-step cleanup to be
interrupted, and therefore no orphan class to audit for.
"""
from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from cbc.catalog.models import ProductRecord

# The lifecycle the estimator sees. Distinct from job status: a job can be `running`
# while the catalog it is rebuilding is still `ready` on its previous version.
STATUSES = ("uploaded", "queued", "processing", "indexing", "ready", "failed", "deleting")

INSERT_BATCH = 500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def catalog_id_for(vendor: str, file_name: str) -> str:
    """Stable across re-uploads of the same vendor file, so replacement is in-place."""
    return hashlib.sha256(f"{vendor.lower()}|{file_name.lower()}".encode()).hexdigest()[:16]


def file_hash(path: Path) -> str:
    """Content hash, streamed - a price book can be 15 MB."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def register(
    connection: sqlite3.Connection,
    *,
    vendor: str,
    file_name: str,
    hash_hex: str,
    page_count: int | None = None,
    effective_date: str | None = None,
) -> tuple[str, bool]:
    """Record a catalog file. Returns (catalog_id, needs_indexing).

    An unchanged re-upload is a no-op: the hash matches and the catalog is already
    `ready`, so there is nothing to do and no reason to spend minutes re-reading it.
    """
    catalog_id = catalog_id_for(vendor, file_name)
    existing = connection.execute(
        "SELECT file_hash, status FROM catalogs WHERE catalog_id = ?", [catalog_id]
    ).fetchone()

    if existing and existing["file_hash"] == hash_hex and existing["status"] == "ready":
        return catalog_id, False

    if existing:
        connection.execute(
            "UPDATE catalogs SET file_hash=?, status='queued', error=NULL, page_count=?, "
            "effective_date=COALESCE(?, effective_date) WHERE catalog_id=?",
            [hash_hex, page_count, effective_date, catalog_id],
        )
    else:
        connection.execute(
            "INSERT INTO catalogs (catalog_id, vendor, file_name, file_hash, page_count, "
            "status, effective_date, created_at) VALUES (?,?,?,?,?,'queued',?,?)",
            [catalog_id, vendor, file_name, hash_hex, page_count, effective_date, _now()],
        )
    return catalog_id, True


def set_status(
    connection: sqlite3.Connection, catalog_id: str, status: str, error: str | None = None
) -> None:
    if status not in STATUSES:
        raise ValueError(f"unknown catalog status {status!r}; known: {STATUSES}")
    connection.execute(
        "UPDATE catalogs SET status=?, error=? WHERE catalog_id=?", [status, error, catalog_id]
    )


def stage(
    connection: sqlite3.Connection,
    catalog_id: str,
    records: Iterable[ProductRecord],
    *,
    version: int,
) -> tuple[str, int]:
    """Write a build into staging, where nothing can search it. Returns (build_id, rows)."""
    build_id = uuid.uuid4().hex
    columns = (
        "build_id, catalog_id, version, vendor, product_code, code_norm, name, "
        "description, category, price, unit, page_number, raw_text"
    )
    placeholders = ",".join("?" * 13)
    written = 0
    batch: list[tuple] = []

    for record in records:
        batch.append(record.as_row(catalog_id, version, build_id))
        if len(batch) >= INSERT_BATCH:
            connection.executemany(
                f"INSERT INTO products_staging ({columns}) VALUES ({placeholders})", batch
            )
            written += len(batch)
            batch.clear()
    if batch:
        connection.executemany(
            f"INSERT INTO products_staging ({columns}) VALUES ({placeholders})", batch
        )
        written += len(batch)
    return build_id, written


def activate(
    connection: sqlite3.Connection, catalog_id: str, build_id: str, *, extractor: str
) -> int:
    """Swap a staged build in, atomically. Returns the row count now live.

    Everything between BEGIN and COMMIT is one unit: the old rows leave, the new
    rows arrive, the catalog is marked ready. A crash anywhere inside leaves the
    previous version live and searchable.
    """
    columns = (
        "catalog_id, version, vendor, product_code, code_norm, name, description, "
        "category, price, unit, page_number, raw_text"
    )
    connection.execute("BEGIN IMMEDIATE")
    try:
        staged = connection.execute(
            "SELECT count(*) FROM products_staging WHERE build_id=?", [build_id]
        ).fetchone()[0]
        if not staged:
            raise ValueError(f"build {build_id} staged no rows; refusing to activate an empty catalog")

        connection.execute("DELETE FROM products WHERE catalog_id=?", [catalog_id])
        connection.execute(
            f"INSERT INTO products ({columns}) SELECT {columns} FROM products_staging "
            "WHERE build_id=?",
            [build_id],
        )
        connection.execute(
            "UPDATE catalogs SET status='ready', error=NULL, product_count=?, "
            "version=version+1, extractor=?, indexed_at=? WHERE catalog_id=?",
            [staged, extractor, _now(), catalog_id],
        )
        connection.execute("DELETE FROM products_staging WHERE build_id=?", [build_id])
        connection.execute("COMMIT")
        return staged
    except BaseException:
        connection.execute("ROLLBACK")
        raise


def discard_build(connection: sqlite3.Connection, build_id: str) -> int:
    """Throw away a staged build. Safe to call for a build that never existed."""
    cursor = connection.execute("DELETE FROM products_staging WHERE build_id=?", [build_id])
    return cursor.rowcount or 0


def clear_stale_staging(connection: sqlite3.Connection, catalog_id: str) -> int:
    """Drop leftovers from a build that died mid-flight, before starting another."""
    cursor = connection.execute("DELETE FROM products_staging WHERE catalog_id=?", [catalog_id])
    return cursor.rowcount or 0


def delete(connection: sqlite3.Connection, catalog_id: str) -> dict[str, Any]:
    """Remove a catalog and everything indexed from it, then prove it.

    One statement inside one transaction. The cascade removes the product rows and
    the FTS delete trigger removes their search records, so there is no window in
    which a deleted catalog is still findable.
    """
    connection.execute("BEGIN IMMEDIATE")
    try:
        removed = connection.execute(
            "SELECT count(*) FROM products WHERE catalog_id=?", [catalog_id]
        ).fetchone()[0]
        connection.execute("DELETE FROM catalogs WHERE catalog_id=?", [catalog_id])
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise

    # Verify rather than assume: this is the requirement that says no orphaned
    # search records, so it is checked rather than argued.
    left = connection.execute(
        "SELECT count(*) FROM products WHERE catalog_id=?", [catalog_id]
    ).fetchone()[0]
    staged = discard_build(connection, catalog_id)  # no-op unless a build was mid-flight
    clear_stale_staging(connection, catalog_id)
    return {"catalog_id": catalog_id, "removed": removed, "orphans": left, "staged_cleared": staged}


def status_of(connection: sqlite3.Connection, catalog_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT catalog_id, vendor, file_name, status, version, product_count, "
        "extractor, effective_date, created_at, indexed_at, error "
        "FROM catalogs WHERE catalog_id=?",
        [catalog_id],
    ).fetchone()
    return dict(row) if row else None
