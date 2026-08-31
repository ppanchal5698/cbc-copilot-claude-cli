#!/usr/bin/env python3
"""Idempotent first-run bootstrap for Docker and fresh installs.

Runs automatically from docker/entrypoint.sh when AUTO_BOOTSTRAP is not 0.

  * Seeds users, price books, and sample catalog rows when the users collection
    is empty.
  * Rebuilds the SQLite catalog index when the index file does not exist yet.

Safe to run on every start: each step no-ops when already satisfied.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def main() -> int:
    from pymongo import MongoClient

    uri = os.environ.get(
        "MONGODB_URI",
        "mongodb://cbc:cbc_local_dev@localhost:27017/cbc_opshub?authSource=admin",
    )
    db_name = os.environ.get("MONGODB_DB", "cbc_opshub")

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.server_info()
        db = client[db_name]
    except Exception as exc:
        print(f"[bootstrap] MongoDB not ready: {exc}")
        return 0  # entrypoint must not block container start

    if db["users"].estimated_document_count() == 0:
        from scripts.seed_db import seed_price_books, seed_products, seed_users

        print("[bootstrap] empty database — seeding users, price books, and catalog")
        seed_users(db)
        seed_price_books(db)
        seed_products(db)
        print("[bootstrap] sign in with estimator@cbc.com or admin@cbc.com / opshub")
    else:
        print("[bootstrap] users already present — skipping database seed")

    index_path = Path(os.environ.get("CATALOG_INDEX_PATH", ROOT / ".index" / "catalog.sqlite3"))
    if not index_path.is_absolute():
        index_path = (ROOT / index_path).resolve()

    if not index_path.exists():
        pricebook_dir = Path(os.environ.get("PRICEBOOK_DIR", ROOT / "pricebooks"))
        if not pricebook_dir.is_absolute():
            pricebook_dir = (ROOT / pricebook_dir).resolve()
        if pricebook_dir.is_dir():
            print(f"[bootstrap] building catalog index at {index_path}")
            from cbc.catalog.rebuild import rebuild

            rebuild(pricebook_dir)
            print("[bootstrap] catalog index ready")
        else:
            print(f"[bootstrap] pricebook dir missing ({pricebook_dir}) — index not built")
    else:
        print("[bootstrap] catalog index already present")

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
