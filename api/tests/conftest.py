"""One place that stands the API up against a throwaway database.

Two things have to happen per test module, and both were getting done wrong when
each module rolled its own fixture:

  * `settings.mongodb_db` is process-global, so setting it at import time means
    the module imported last picks the database for every module. The name has
    to be set when the fixture runs, not when the file is read.
  * `api.db` holds one motor client, and motor binds its sockets to the event
    loop that first used them. TestClient closes its loop on exit, so a client
    carried into a second module raises "Event loop is closed" on every query.
    Dropping the singleton either side of the run rebuilds it on the live loop.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


@contextmanager
def opshub_client(db_name: str) -> Iterator["object"]:
    from fastapi.testclient import TestClient
    from pymongo import MongoClient

    from api import db as db_module
    from api.config import settings
    from api.main import app

    settings.mongodb_db = db_name
    db_module._client = None

    raw = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
    try:
        raw.server_info()
    except Exception:
        pytest.skip("MongoDB is not running - start it with `docker compose up -d`")
    raw.drop_database(db_name)

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        raw.drop_database(db_name)
        db_module._client = None
        raw.close()
