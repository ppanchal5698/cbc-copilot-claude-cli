"""Concurrency and recovery, against a real MongoDB.

Everything here is a production failure mode that local development never
reproduces: a worker killed mid-run, two estimators clicking at the same moment,
two vendors selling the same part number. They need the real indexes, so they
need the real database.

    docker compose up -d mongo && python -m pytest tests/api/test_recovery.py -q
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest
from pymongo import MongoClient

from api import db as db_module
from api.config import settings

TEST_DB = "cbc_opshub_test_recovery"


@pytest.fixture()
def database():
    """A throwaway database with the real indexes built on it."""
    raw = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
    try:
        raw.server_info()
    except Exception as exc:
        if os.environ.get("REQUIRE_MONGO"):
            pytest.fail(f"REQUIRE_MONGO is set but MongoDB is not reachable: {exc}")
        pytest.skip("MongoDB is not running - start it with `docker compose up -d mongo`")

    previous, settings.mongodb_db = settings.mongodb_db, TEST_DB
    raw.drop_database(TEST_DB)
    db_module._client = None

    asyncio.run(db_module.ensure_indexes())
    db_module._client = None
    try:
        yield raw[TEST_DB]
    finally:
        raw.drop_database(TEST_DB)
        raw.close()
        settings.mongodb_db = previous
        db_module._client = None


def run(coro):
    """Each test gets its own loop, so the motor client binds to it."""
    db_module._client = None
    try:
        return asyncio.run(coro)
    finally:
        db_module._client = None


def _now():
    return datetime.now(timezone.utc)


# ── a killed worker must not wedge the bid forever ─────────────────────────


def test_a_stale_running_job_is_reaped_and_requeued(database) -> None:
    """`running` with no heartbeat means the process that claimed it is gone.

    Left alone the job stays `running` for ever, and because the exclusive-job
    index counts it as in flight, that bid can never be re-extracted again.
    """
    from bson import ObjectId

    project_id = ObjectId()
    database["jobs"].insert_one(
        {
            "type": "extract_bid_set",
            "projectId": project_id,
            "status": "running",
            "attempts": 1,
            "createdAt": _now(),
            "heartbeatAt": _now() - timedelta(minutes=10),
        }
    )

    from worker.main import reap_abandoned

    assert run(reap_abandoned()) == 1

    job = database["jobs"].find_one({"projectId": project_id})
    assert job["status"] == "queued"
    assert job["heartbeatAt"] is None
    assert "worker stopped" in job["error"]


def test_a_job_with_a_fresh_heartbeat_is_left_alone(database) -> None:
    """Another worker is genuinely running it. Reaping would double-run the bid."""
    from bson import ObjectId

    database["jobs"].insert_one(
        {
            "type": "match_and_price",
            "projectId": ObjectId(),
            "status": "running",
            "attempts": 1,
            "createdAt": _now(),
            "heartbeatAt": _now(),
        }
    )

    from worker.main import reap_abandoned

    assert run(reap_abandoned()) == 0
    assert database["jobs"].find_one({})["status"] == "running"


def test_a_reaped_job_that_is_out_of_attempts_fails(database) -> None:
    from bson import ObjectId

    from worker.main import MAX_ATTEMPTS, reap_abandoned

    database["jobs"].insert_one(
        {
            "type": "extract_bid_set",
            "projectId": ObjectId(),
            "status": "running",
            "attempts": MAX_ATTEMPTS,
            "createdAt": _now(),
            "heartbeatAt": None,
        }
    )

    run(reap_abandoned())
    assert database["jobs"].find_one({})["status"] == "failed"


def test_a_requeued_job_waits_for_its_backoff(database) -> None:
    """Without a delay a job that fails in two seconds burns three attempts in six."""
    from worker.main import claim

    database["jobs"].insert_one(
        {
            "type": "extract_bid_set",
            "projectId": None,
            "status": "queued",
            "attempts": 1,
            "createdAt": _now(),
            "nextAttemptAt": _now() + timedelta(minutes=5),
        }
    )
    assert run(claim()) is None, "claimed a job that is still backing off"

    database["jobs"].update_one({}, {"$set": {"nextAttemptAt": _now() - timedelta(seconds=1)}})
    assert run(claim()) is not None, "a due job was not claimed"


# ── the exclusive-job index must encode the same policy as the code ────────


def test_two_price_book_ingests_can_queue_together(database) -> None:
    """Both carry no project, so the old index keyed them both on (null, type).

    The second upload was handed back the first one's job and its sheet was never
    read - while the API reported success.
    """
    from api.services.jobs import enqueue

    async def both():
        return (
            await enqueue("ingest_pricebook", payload={"filename": "hager.pdf"}),
            await enqueue("ingest_pricebook", payload={"filename": "rockwood.pdf"}),
        )

    first, second = run(both())

    assert first["_id"] != second["_id"], "the second price book was silently dropped"
    assert database["jobs"].count_documents({"type": "ingest_pricebook"}) == 2


def test_a_second_extraction_on_one_bid_is_still_the_same_job(database) -> None:
    """The double-click guard this index exists for still has to work."""
    from bson import ObjectId

    from api.services.jobs import enqueue

    project_id = ObjectId()

    async def twice():
        return (
            await enqueue("extract_bid_set", project_id=project_id),
            await enqueue("extract_bid_set", project_id=project_id),
        )

    first, second = run(twice())
    assert first["_id"] == second["_id"]


# ── two vendors, one part number ───────────────────────────────────────────


def test_the_same_part_from_two_manufacturers_coexists(database) -> None:
    """Keyed on `part` alone, the ingest upserted one vendor's row over another's."""
    from bson import ObjectId

    from worker.handlers.ingest import ingest_pricebook

    cache = settings.repo_root / ".cache"
    cache.mkdir(parents=True, exist_ok=True)

    def sheet(manufacturer: str, cost: float, book_id) -> dict:
        path = cache / f"pricebook-{manufacturer}.json"
        path.write_text(
            f'{{"products": [{{"part": "1234", "manufacturer": "{manufacturer}", '
            f'"cost": {cost}}}]}}',
            encoding="utf-8",
        )
        return {
            "type": "ingest_pricebook",
            "payload": {"outputPath": f".cache/{path.name}", "priceBookId": str(book_id)},
        }

    hager, rockwood = ObjectId(), ObjectId()
    database["priceBooks"].insert_many([{"_id": hager}, {"_id": rockwood}])

    async def both():
        await ingest_pricebook(sheet("Hager", 10.0, hager))
        await ingest_pricebook(sheet("Rockwood", 20.0, rockwood))

    run(both())

    rows = {row["manufacturer"]: row["cost"] for row in database["products"].find({"part": "1234"})}
    assert rows == {"Hager": 10.0, "Rockwood": 20.0}


def test_an_ingest_without_a_date_keeps_the_one_purchasing_entered(database) -> None:
    """Writing null over it made a lapsed sheet report `stale: false`."""
    from bson import ObjectId

    from worker.handlers.ingest import ingest_pricebook

    book_id = ObjectId()
    database["priceBooks"].insert_one({"_id": book_id, "effective": "2020-01-01"})

    cache = settings.repo_root / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "pricebook-undated.json"
    path.write_text('{"products": [{"part": "X1", "manufacturer": "ASI"}]}', encoding="utf-8")

    run(
        ingest_pricebook(
            {
                "type": "ingest_pricebook",
                "payload": {"outputPath": ".cache/pricebook-undated.json",
                            "priceBookId": str(book_id)},
            }
        )
    )

    assert database["priceBooks"].find_one({"_id": book_id})["effective"] == "2020-01-01"


# ── numbering under concurrency ────────────────────────────────────────────


def test_concurrent_bids_get_distinct_codes(database) -> None:
    """Both used to compute max+1 from a scan; the second got a duplicate-key 500."""
    from api.routers.projects import next_code

    async def ten_at_once():
        return await asyncio.gather(*(next_code() for _ in range(10)))

    codes = run(ten_at_once())
    assert len(set(codes)) == 10, f"codes collided: {sorted(codes)}"


def test_the_code_counter_continues_an_existing_series(database) -> None:
    """A database issued codes before the counter existed; do not restart on them."""
    from api.services import storage
    from api.routers.projects import next_code

    prefix = storage.code_prefix()
    database["projects"].insert_one({"code": f"{prefix}0007", "slug": "old"})

    assert run(next_code()) == f"{prefix}0008"


def test_two_versions_cannot_share_a_number(database) -> None:
    """Two addenda both became version n+1 and the diff attached to either one."""
    from bson import ObjectId

    from api.routers.versions import snapshot

    project = {"_id": ObjectId(), "slug": "concurrent-addenda"}

    async def two_snapshots():
        return await asyncio.gather(
            snapshot(project, "Addendum 1", "rick"),
            snapshot(project, "Addendum 2", "shanna"),
        )

    versions = run(two_snapshots())
    assert {v["version"] for v in versions} == {1, 2}
