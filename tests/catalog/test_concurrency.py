"""Searching while a catalog is being indexed, replaced or deleted.

`async` does not make SQLite concurrent, and this is where that gets checked. The
guarantees being tested are specific:

  * WAL means readers never block on the writer, and the writer never blocks on
    readers. A pricing pass keeps working while purchasing uploads a sheet.
  * There is exactly one writer - the worker. Everything else opens `query_only`,
    so "read-only" is enforced by the database rather than by convention.
  * A catalog being replaced is searchable throughout: the new build is staged
    invisibly and swapped in one transaction.
"""
from __future__ import annotations

import sqlite3
import threading
import time

import pytest

from catalog_index import db, registry, search
from catalog_index.models import ProductRecord


def _records(vendor: str, count: int, prefix: str) -> list[ProductRecord]:
    return [
        ProductRecord(vendor, (n % 40) + 1, f"{prefix}{n:04d}", f"{prefix} part {n}",
                      "stainless steel assembly", "hardware", 10.0 + n, "EA")
        for n in range(count)
    ]


@pytest.fixture()
def index_file(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    writer = db.initialise(path)
    catalog_id, _ = registry.register(
        writer, vendor="hager", file_name="hager.pdf", hash_hex="v1")
    build, _ = registry.stage(writer, catalog_id, _records("hager", 400, "AA"), version=1)
    registry.activate(writer, catalog_id, build, extractor="test")
    writer.close()
    return path


def test_wal_is_on(index_file) -> None:
    """Everything below depends on it."""
    writer = db.connect(index_file, readonly=False)
    try:
        assert writer.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        writer.close()


def test_searches_keep_working_while_a_catalog_indexes(index_file) -> None:
    """The pricing pass must not stall because purchasing uploaded a sheet."""
    stop = threading.Event()
    counts: list[int] = []
    errors: list[str] = []

    def reader() -> None:
        connection = db.connect(index_file, readonly=True)
        try:
            while not stop.is_set():
                try:
                    counts.append(search.search(connection, "stainless steel")["count"])
                except Exception as exc:  # SQLITE_BUSY would land here
                    errors.append(repr(exc))
        finally:
            connection.close()

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    writer = db.connect(index_file, readonly=False)
    try:
        second, _ = registry.register(
            writer, vendor="bobrick", file_name="bobrick.pdf", hash_hex="v1")
        for round_number in range(4):
            build, _ = registry.stage(
                writer, second, _records("bobrick", 300, f"B{round_number}"), version=1)
            registry.activate(writer, second, build, extractor="test")
            registry.delete(writer, second)
            registry.register(
                writer, vendor="bobrick", file_name="bobrick.pdf", hash_hex="v1")
    finally:
        writer.close()
        stop.set()
        thread.join(timeout=10)

    assert not errors, f"readers were blocked or errored: {errors[:3]}"
    assert counts, "the reader never completed a search"
    assert all(c > 0 for c in counts), "a search came back empty mid-index"


def test_a_catalog_stays_searchable_across_a_replacement(index_file) -> None:
    """The failure to avoid: the vendor disappears while the new sheet indexes."""
    writer = db.connect(index_file, readonly=False)
    reader = db.connect(index_file, readonly=True)
    try:
        catalog_id = search.list_catalogs(writer)[0]["catalog_id"]
        seen: list[int] = []

        # Build the replacement while watching. Staged rows are invisible, so the
        # old version has to answer every one of these.
        build, _ = registry.stage(writer, catalog_id, _records("hager", 400, "CC"), version=2)
        for _ in range(5):
            seen.append(search.search(reader, "stainless steel")["count"])
            time.sleep(0.01)

        registry.activate(writer, catalog_id, build, extractor="test")
        seen.append(search.search(reader, "stainless steel")["count"])

        assert all(count > 0 for count in seen), f"the catalog went dark: {seen}"
        # And the swap really happened.
        assert search.search(reader, "CC0001")["count"] == 1
        assert search.search(reader, "AA0001")["count"] == 0
    finally:
        reader.close()
        writer.close()


def test_only_one_connection_may_write(index_file) -> None:
    """Single-writer is the model SQLite actually supports, so it is enforced."""
    reader = db.connect(index_file, readonly=True)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly|read-only"):
            reader.execute("DELETE FROM products")
        with pytest.raises(sqlite3.OperationalError):
            reader.execute(
                "INSERT INTO catalogs (catalog_id, vendor, file_name, file_hash, status, "
                "created_at) VALUES ('x','v','f','h','ready','now')"
            )
    finally:
        reader.close()


def test_a_deleted_catalog_disappears_from_a_live_reader(index_file) -> None:
    """A search running when a catalog is deleted must not return its products."""
    writer = db.connect(index_file, readonly=False)
    reader = db.connect(index_file, readonly=True)
    try:
        assert search.search(reader, "AA0001")["count"] == 1
        catalog_id = search.list_catalogs(writer)[0]["catalog_id"]
        report = registry.delete(writer, catalog_id)

        assert report["orphans"] == 0
        assert search.search(reader, "AA0001")["count"] == 0, "a deleted product is still findable"
        assert db.integrity_report(writer)["ok"]
    finally:
        reader.close()
        writer.close()


def test_indexing_the_same_catalog_twice_does_not_duplicate_it(index_file) -> None:
    """Two workers, or a retry after a crash, must converge on one version."""
    writer = db.connect(index_file, readonly=False)
    try:
        catalog_id = search.list_catalogs(writer)[0]["catalog_id"]
        for _ in range(3):
            build, _ = registry.stage(writer, catalog_id, _records("hager", 50, "AA"), version=9)
            registry.activate(writer, catalog_id, build, extractor="test")

        assert writer.execute("SELECT count(*) FROM products").fetchone()[0] == 50
        assert writer.execute("SELECT count(*) FROM products_staging").fetchone()[0] == 0
        assert db.integrity_report(writer)["ok"]
    finally:
        writer.close()
