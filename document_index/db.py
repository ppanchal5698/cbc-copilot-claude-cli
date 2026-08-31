"""SQLite connections for per-document content.db files."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from catalog_index.db import assert_safe_location

SCHEMA = Path(__file__).resolve().parent / "schema.sql"
BUSY_TIMEOUT_MS = 5_000


def connect(path: Path, *, readonly: bool = True) -> sqlite3.Connection:
    """Open a content.db. Readers use query_only like the catalog index."""
    if not readonly:
        path.parent.mkdir(parents=True, exist_ok=True)
    assert_safe_location(path)

    connection = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA foreign_keys=ON")
    if readonly:
        connection.execute("PRAGMA query_only=1")
    else:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
    return connection


def initialise(path: Path) -> sqlite3.Connection:
    connection = connect(path, readonly=False)
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    return connection
