"""Connections to the search index, and the rules about where it may live.

Two things here are not incidental.

**The filesystem matters.** SQLite needs real POSIX advisory locking, and WAL needs
shared memory it can mmap. A 9p bind mount (Docker Desktop on Windows), NFS, EFS or
SMB gives neither reliably, and the failure is silent corruption rather than an
error. `/app/projects` in this stack *is* 9p, so the index deliberately does not
live there - it goes on a named Docker volume, which is ext4. `assert_safe_location`
refuses to open the database from a known-unsafe filesystem instead of finding out
later.

**Readers are `query_only`, not `mode=ro`.** A read-only *file* handle cannot read a
WAL database: WAL readers have to map the `-shm` file, which needs write access to
it. Opening `file:...?mode=ro` therefore fails exactly when the index is in use.
`PRAGMA query_only=1` gives the same guarantee - the connection rejects every write -
while letting WAL work. That is why the volume is mounted read-write on both
containers even though only the worker writes.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from cbc_core.paths import repo_root

REPO_ROOT = repo_root()
SCHEMA = Path(__file__).resolve().parent / "schema.sql"

# Filesystems where SQLite locking is not dependable. Names as they appear in
# /proc/mounts; the check is a no-op on hosts without it (Windows dev machines).
UNSAFE_FILESYSTEMS = frozenset(
    {"9p", "fuse", "fuseblk", "fuse.gcsfuse", "nfs", "nfs4", "cifs", "smbfs",
     "virtiofs", "vboxsf", "lustre", "glusterfs"}
)

BUSY_TIMEOUT_MS = 5_000


def index_path() -> Path:
    """Where the index file lives. Override with CATALOG_INDEX_PATH."""
    configured = os.environ.get("CATALOG_INDEX_PATH")
    if configured:
        return Path(configured)
    return REPO_ROOT / ".index" / "catalog.sqlite3"


def filesystem_of(path: Path) -> str | None:
    """The filesystem type backing `path`, or None when it cannot be determined."""
    mounts = Path("/proc/mounts")
    if not mounts.exists():
        return None  # not Linux; the container check is the one that matters
    try:
        target = path.resolve()
    except OSError:
        return None

    best: tuple[int, str] | None = None
    for line in mounts.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        mount_point, fs_type = parts[1], parts[2]
        try:
            candidate = Path(mount_point).resolve()
        except OSError:
            continue
        if candidate == target or candidate in target.parents:
            depth = len(candidate.parts)
            if best is None or depth > best[0]:
                best = (depth, fs_type)
    return best[1] if best else None


def assert_safe_location(path: Path) -> None:
    """Refuse to put the index somewhere SQLite cannot lock it correctly."""
    if os.environ.get("CATALOG_INDEX_ALLOW_UNSAFE_FS"):
        return
    fs_type = filesystem_of(path.parent)
    if fs_type and fs_type.split(".")[0] in {f.split(".")[0] for f in UNSAFE_FILESYSTEMS}:
        raise RuntimeError(
            f"the catalog index cannot live on a {fs_type!r} filesystem ({path.parent}). "
            "SQLite needs dependable POSIX locking and WAL needs shared memory, and "
            "neither is reliable there - the failure mode is corruption, not an error. "
            "Mount a named Docker volume for it (see docker-compose.yml), or set "
            "CATALOG_INDEX_ALLOW_UNSAFE_FS=1 if you accept the risk."
        )


def connect(path: Path | None = None, *, readonly: bool = True) -> sqlite3.Connection:
    """Open the index. Readers get a connection that physically cannot write."""
    target = path or index_path()
    if not readonly:
        target.parent.mkdir(parents=True, exist_ok=True)
    assert_safe_location(target)

    connection = sqlite3.connect(target, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA foreign_keys=ON")  # per connection, or CASCADE is inert
    if readonly:
        connection.execute("PRAGMA query_only=1")
    else:
        connection.execute("PRAGMA journal_mode=WAL")
        # The index is rebuildable from the PDFs, so paying an fsync per commit to
        # protect it against power loss buys nothing a rebuild would not.
        connection.execute("PRAGMA synchronous=NORMAL")
    return connection


def initialise(path: Path | None = None) -> sqlite3.Connection:
    """Create the index if it is not there, and return a writable connection."""
    connection = connect(path, readonly=False)
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    return connection


def integrity_report(connection: sqlite3.Connection) -> dict[str, object]:
    """Is the FTS index consistent with its content table, and are there orphans?"""
    problems: list[str] = []
    try:
        connection.execute("INSERT INTO products_fts(products_fts) VALUES('integrity-check')")
    except sqlite3.DatabaseError as exc:
        problems.append(f"fts integrity-check failed: {exc}")

    orphans = connection.execute(
        "SELECT count(*) FROM products p "
        "LEFT JOIN catalogs c ON c.catalog_id = p.catalog_id WHERE c.catalog_id IS NULL"
    ).fetchone()[0]
    if orphans:
        problems.append(f"{orphans} product row(s) with no catalog")

    indexed = connection.execute("SELECT count(*) FROM products").fetchone()[0]
    searchable = connection.execute("SELECT count(*) FROM products_fts").fetchone()[0]
    if indexed != searchable:
        problems.append(f"products={indexed} but products_fts={searchable}")

    return {"ok": not problems, "problems": problems, "products": indexed}
