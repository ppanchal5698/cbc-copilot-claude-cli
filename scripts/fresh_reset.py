#!/usr/bin/env python3
"""Wipe Ops-Hub to a clean slate — dev sign-in accounts only.

Removes all bids, price books, catalog rows, jobs, and on-disk project workspaces.
Resets pricebooks/ and the SQLite catalog index. Re-seeds only the two local
developer accounts (estimator@cbc.com, admin@cbc.com).

    python scripts/fresh_reset.py
    python scripts/fresh_reset.py --yes   # skip confirmation prompt
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

URI = "mongodb://cbc:cbc_local_dev@localhost:27017/cbc_opshub?authSource=admin"

COLLECTIONS = (
    "users",
    "projects",
    "documents",
    "lineItems",
    "quoteLines",
    "quotes",
    "proposals",
    "products",
    "priceBooks",
    "jobs",
    "auditLog",
    "calls",
    "estimateVersions",
    "counters",
    "settings",
)

PRICEBOOK_KEEP = frozenset({"index.json", "README.md"})


def reset_mongo(uri: str, db_name: str) -> None:
    from scripts.seed_db import seed_users

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.server_info()
    db = client[db_name]

    for name in COLLECTIONS:
        db[name].drop()

    count = seed_users(db)
    client.close()
    print(f"mongodb      dropped {len(COLLECTIONS)} collections, seeded {count} users")


def reset_pricebooks(pricebook_dir: Path) -> None:
    removed = 0
    for path in pricebook_dir.iterdir():
        if not path.is_file() or path.name in PRICEBOOK_KEEP:
            continue
        path.unlink(missing_ok=True)
        removed += 1

    index = {
        "description": "Inventory of CBC vendor price books. Read-only during a pipeline run.",
        "generated_from": "final_pricebooks/",
        "refresh_cadence": "UNDEFINED - see .claude/rules/data-stewardship.md (NFR-10, OPEN)",
        "pricebooks": [],
    }
    (pricebook_dir / "index.json").write_text(
        json.dumps(index, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"pricebooks   removed {removed} files, index.json cleared")


def reset_projects(storage_root: Path) -> None:
    removed = 0
    for path in storage_root.iterdir():
        if path.name == ".gitkeep":
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    print(f"projects     removed {removed} workspace(s)")


def reset_catalog_index() -> None:
    """Drop the Docker catalog volume and rebuild an empty index."""
    subprocess.run(["docker", "compose", "stop", "api", "worker"], cwd=ROOT, check=False)
    subprocess.run(["docker", "compose", "rm", "-sf", "api", "worker"], cwd=ROOT, check=False)

    listed = subprocess.run(
        ["docker", "volume", "ls", "-q", "--filter", "name=catalog_index"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    for volume in listed.stdout.splitlines():
        volume = volume.strip()
        if volume:
            subprocess.run(["docker", "volume", "rm", volume], cwd=ROOT, check=False)

    subprocess.run(["docker", "compose", "up", "-d", "api", "worker"], cwd=ROOT, check=True)

    # Bootstrap creates the index when missing; with an empty pricebooks/ dir it stays empty.
    for _ in range(30):
        probe = subprocess.run(
            [
                "docker", "exec", "cbc-api", "python", "-c",
                "import sqlite3, os; p=os.environ.get('CATALOG_INDEX_PATH','/app/.index/catalog.sqlite3'); "
                "print('missing' if not os.path.exists(p) else sqlite3.connect(p).execute("
                "'select count(*) from products').fetchone()[0])",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode == 0 and probe.stdout.strip() in {"0", "missing"}:
            break
        import time
        time.sleep(2)

    print("catalog      catalog_index volume reset (empty index)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", "-y", action="store_true", help="skip confirmation")
    parser.add_argument("--uri", default=None)
    parser.add_argument("--skip-docker", action="store_true", help="only reset Mongo and local folders")
    args = parser.parse_args()

    if not args.yes:
        print(
            "This removes ALL bids, price books, catalog data, and project files.\n"
            "Only estimator@cbc.com and admin@cbc.com will remain.\n"
        )
        if input("Continue? [y/N] ").strip().lower() not in {"y", "yes"}:
            print("Aborted.")
            return 1

    uri = args.uri or os.environ.get("MONGODB_URI", URI)
    db_name = os.environ.get("MONGODB_DB", "cbc_opshub")

    reset_mongo(uri, db_name)
    reset_pricebooks(ROOT / "pricebooks")
    reset_projects(ROOT / "projects")

    if not args.skip_docker:
        try:
            reset_catalog_index()
        except subprocess.CalledProcessError as exc:
            print(f"catalog      docker reset skipped ({exc})")
            print("             run `docker compose up -d` and delete the catalog_index volume manually")
    else:
        local_index = ROOT / ".index" / "catalog.sqlite3"
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(local_index) + suffix)
            path.unlink(missing_ok=True)
        print("catalog      local .index cleared (--skip-docker)")

    print("\nFresh install ready. Sign in with estimator@cbc.com or admin@cbc.com / opshub")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
