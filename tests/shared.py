"""Shared test helpers imported by conftest and individual test modules."""
from __future__ import annotations

import os
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for extra in (
    ROOT / "mcp-servers",
    ROOT / ".claude" / "skills" / "extract-door-schedule" / "scripts",
    ROOT / ".claude" / "skills" / "generate-quotation" / "scripts",
):
    sys.path.insert(0, str(extra))

FIXTURE_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "1_Architectural.pdf"
SCHEDULE_PAGE = 14  # sheet A2.2 in the Dutch Bros fixture


TEST_ACTOR = "test@example.com"


@contextmanager
def opshub_client(
    db_name: str, *, isolated_storage: bool = False, role: str = "admin"
) -> Iterator["object"]:
    from fastapi.testclient import TestClient
    from pymongo import MongoClient

    from api import db as db_module
    from api.config import settings
    from api.main import app

    settings.mongodb_db = db_name
    db_module._client = None

    scratch: Path | None = None
    previous_storage = settings.storage_root
    if isolated_storage:
        scratch = ROOT / "tests" / "fixtures" / "scratch" / db_name
        scratch.mkdir(parents=True, exist_ok=True)
        settings.storage_root = scratch

    raw = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
    try:
        raw.server_info()
    except Exception as exc:
        # Skipping keeps a laptop without Docker usable. It also meant the entire
        # API suite went green on a codebase whose API could not even be imported,
        # so anywhere it matters - CI - REQUIRE_MONGO turns the skip into a
        # failure. A suite that reports success while testing nothing is worse
        # than one that does not run.
        message = f"MongoDB is not reachable at {settings.mongodb_uri.split('@')[-1]}: {exc}"
        if os.environ.get("REQUIRE_MONGO"):
            pytest.fail(f"REQUIRE_MONGO is set but {message}")
        pytest.skip(f"{message} - start it with `docker compose up -d mongo`")
    raw.drop_database(db_name)

    # The signed-in actor is a real person with a role. Authorization on the
    # provider settings and the destructive price-book route reads it from the
    # database rather than from a header, because the internal token
    # authenticates the Next.js server and not the human behind it.
    raw[db_name]["users"].insert_one(
        {"email": TEST_ACTOR, "name": "Test Estimator", "role": role}
    )

    try:
        headers = {
            "X-Internal-Token": settings.internal_api_token,
            "X-Actor": TEST_ACTOR,
        }
        with TestClient(app, headers=headers) as test_client:
            yield test_client
    finally:
        raw.drop_database(db_name)
        db_module._client = None
        raw.close()
        settings.storage_root = previous_storage
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
