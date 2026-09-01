"""What a pass wrote on disk, landing in MongoDB.

This is the seam between the two actors - Claude writes JSON, the worker syncs it -
and it had no tests. Every failure here is silent by construction: a shape the
importer does not recognise produces zero openings and a clean "done", and the
estimator sees an empty bid rather than an error.

Frozen artifacts, no Claude. The point is the importer, not the extraction.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil

import pytest
from bson import ObjectId
from pymongo import MongoClient

from cbc.config import settings
from tests.shared import ROOT

TEST_DB = "cbc_test_sync_import"
SLUG = "sync_import_fixture"


def run(coro):
    """Each test gets its own loop, so the motor client binds to it."""
    from cbc import db as db_module

    db_module._client = None
    try:
        return asyncio.run(coro)
    finally:
        db_module._client = None


@pytest.fixture()
def project():
    """A throwaway database and an isolated projects/ root, with one bid in it."""
    from cbc import db as db_module

    raw = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
    try:
        raw.server_info()
    except Exception as exc:
        if os.environ.get("REQUIRE_MONGO"):
            pytest.fail(f"REQUIRE_MONGO is set but MongoDB is not reachable: {exc}")
        pytest.skip("MongoDB is not running - start it with `docker compose up -d mongo`")

    previous_db, settings.mongodb_db = settings.mongodb_db, TEST_DB
    previous_root = settings.storage_root
    scratch = ROOT / "tests" / "fixtures" / "scratch" / TEST_DB
    shutil.rmtree(scratch, ignore_errors=True)
    settings.storage_root = scratch
    raw.drop_database(TEST_DB)
    db_module._client = None

    record = {"_id": ObjectId(), "slug": SLUG, "code": "SY-001", "name": "Sync fixture"}
    raw[TEST_DB]["projects"].insert_one(dict(record))

    try:
        yield record, raw[TEST_DB], scratch / SLUG
    finally:
        raw.drop_database(TEST_DB)
        raw.close()
        settings.mongodb_db = previous_db
        settings.storage_root = previous_root
        shutil.rmtree(scratch, ignore_errors=True)
        db_module._client = None


def _write(directory, relative, payload):
    path = directory / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _opening(number: str, **overrides):
    base = {
        "door_number": number,
        "size": "3070",
        "handing": "LH",
        "finish": "US26D",
        "fire_rating": "90",
        "source_page": 14,
        "source_file": "bid.pdf",
        "page_size": {"width": 612, "height": 792},
        "bbox": [72, 300, 320, 316],
        "confidence": 0.92,
    }
    base.update(overrides)
    return base


# ── extraction ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "shape",
    [
        pytest.param(lambda rows: rows, id="bare-array"),
        pytest.param(lambda rows: {"openings": rows}, id="openings-wrapper"),
        pytest.param(lambda rows: {"lines": rows}, id="lines-wrapper"),
    ],
)
def test_every_shape_a_pass_has_written_is_imported(project, shape) -> None:
    """Three shapes have come out of real runs. All three must import.

    A shape the importer does not recognise yields zero openings and reports
    success, which is the worst available outcome: the bid looks empty rather
    than broken.
    """
    from cbc.services import sync

    record, database, directory = project
    _write(directory, "extracted/door_schedule.json", shape([_opening("101"), _opening("102")]))

    counts = run(sync.import_extraction(record))

    assert counts["inserted"] == 2, counts
    assert database["lineItems"].count_documents({"projectId": record["_id"]}) == 2


def test_importing_twice_updates_rather_than_duplicates(project) -> None:
    """A rerun must not double the schedule."""
    from cbc.services import sync

    record, database, directory = project
    _write(directory, "extracted/door_schedule.json", {"openings": [_opening("101")]})
    run(sync.import_extraction(record))

    _write(
        directory,
        "extracted/door_schedule.json",
        {"openings": [_opening("101", finish="US32D")]},
    )
    second = run(sync.import_extraction(record))

    assert database["lineItems"].count_documents({"projectId": record["_id"]}) == 1
    assert second["inserted"] == 0
    stored = database["lineItems"].find_one({"projectId": record["_id"]})
    assert stored["finish"] == "US32D", "a rerun must carry the correction through"


def test_scope_metadata_lands_on_the_project(project) -> None:
    from cbc.services import sync

    record, database, directory = project
    _write(
        directory,
        "extracted/scope_metadata.json",
        {"project_name": "Dutch Bros MacArthur", "state": "OH", "architect": "HDA"},
    )

    assert run(sync.import_scope_metadata(record)) is True
    stored = database["projects"].find_one({"_id": record["_id"]})
    assert stored.get("state") == "OH"


# ── pricing ─────────────────────────────────────────────────────────────────


def _line(line_id: str, **overrides):
    base = {
        "line_id": line_id,
        "group": "Door 101",
        "group_type": "door",
        "part_number": "3400",
        "description": "Hager 3400 lockset",
        "division": "08 71 00",
        "quantity": 2,
        "cost": 100.0,
        "margin": 0.27,
        "sale_ea": 136.99,
        "ext_price": 273.98,
        "cost_source": "LIST_X_MULTIPLIER",
        "cost_source_detail": "hager_price_book_18.pdf PDF p42",
        "source_page": 14,
        "flags": [],
    }
    base.update(overrides)
    return base


def test_priced_lines_are_imported(project) -> None:
    from cbc.services import sync

    record, database, directory = project
    _write(directory, "priced/line_items.json", {"lines": [_line("L1"), _line("L2")]})

    counts = run(sync.import_quote_lines(record))

    assert counts["inserted"] == 2, counts
    assert database["quoteLines"].count_documents({"projectId": record["_id"]}) == 2


def test_a_manual_line_keeps_a_null_cost(project) -> None:
    """NR-13. A number here would be an invented price that looks finished."""
    from cbc.services import sync

    record, database, directory = project
    _write(
        directory,
        "priced/line_items.json",
        {"lines": [_line("L1", cost=None, sale_ea=None, ext_price=None,
                          cost_source="MANUAL",
                          cost_source_detail="9ft leaf - custom size, no catalog price")]},
    )
    run(sync.import_quote_lines(record))

    stored = database["quoteLines"].find_one({"projectId": record["_id"]})
    assert stored["cost"] is None
    assert stored["costSource"] == "MANUAL"


def test_a_negative_cost_is_flagged_rather_than_stored(project) -> None:
    """The schema bounds what an estimator types; a run writes straight through."""
    from cbc.services import sync

    record, database, directory = project
    _write(directory, "priced/line_items.json", {"lines": [_line("L1", cost=-45)]})
    run(sync.import_quote_lines(record))

    stored = database["quoteLines"].find_one({"projectId": record["_id"]})
    assert stored["cost"] is None
    assert any("negative" in flag for flag in stored.get("flags", []))


# ── proposal ────────────────────────────────────────────────────────────────


def test_proposal_artifacts_are_recorded_when_present(project) -> None:
    from cbc.services import sync

    record, _database, directory = project
    (directory).mkdir(parents=True, exist_ok=True)
    (directory / "quotation.html").write_text("<html>quote</html>", encoding="utf-8")
    _write(directory, "review/review_flags.json", [])

    written = run(sync.import_proposal_artifacts(record))

    assert written["quotationHtml"] is True
    assert written["reviewFlags"] is True


def test_a_missing_artifact_is_reported_as_missing(project) -> None:
    """Not an exception, and not silently true - the proposal screen reads this."""
    from cbc.services import sync

    record, _database, _directory = project
    written = run(sync.import_proposal_artifacts(record))
    assert all(present is False for present in written.values()), written


# ── nothing on disk ─────────────────────────────────────────────────────────


def test_an_absent_schedule_imports_nothing_and_does_not_raise(project) -> None:
    """A pass that wrote no schedule is a failed pass, and the gate reports it.

    The importer's job is to be honest about finding nothing, not to invent an
    error the validation layer already raises with a better message.
    """
    from cbc.services import sync

    record, database, _directory = project
    counts = run(sync.import_extraction(record))

    assert counts["inserted"] == 0
    assert database["lineItems"].count_documents({"projectId": record["_id"]}) == 0
