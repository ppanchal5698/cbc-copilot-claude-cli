"""Job queue - how the estimator's actions reach Claude Code.

The API enqueues; the worker in `worker/` claims and runs. Nothing here spawns a
process: extraction on a 30-page CAD set is minutes of work, far longer than a
web request should hold open, and a dropped connection must not lose the job.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from cbc.db import db
from cbc.schemas.common import EXCLUSIVE_JOB_TYPES
from cbc.services import audit

EXCLUSIVE = set(EXCLUSIVE_JOB_TYPES)


def _due(delay_seconds: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)


# Project-less job types, and the payload field that identifies the same work.
# Indexing is idempotent on the file hash, so a second pass over an unchanged
# sheet is pure waste - and two at once are a write race.
COALESCE_BY_PAYLOAD = {"index_catalog": "filename"}


async def enqueue(
    job_type: str,
    project_id: ObjectId | None = None,
    payload: dict[str, Any] | None = None,
    actor: str = "estimator",
    delay_seconds: int = 0,
) -> dict[str, Any]:
    """Queue a job. `delay_seconds` holds it back so a burst can coalesce.

    A bid set is often several PDFs, and a run reads the whole of uploads/raw/. A
    pipeline that started on the first file would simply not see the next two, so
    the upload route asks for a short delay and each further upload pushes it out.
    """
    # Job types that carry no project, so the per-project exclusivity below cannot
    # see them. Re-uploading the same sheet twice in a minute - which the
    # price-books screen makes easy - queued two indexing passes that raced to
    # write the same pageIndex document.
    coalesce_key = COALESCE_BY_PAYLOAD.get(job_type)
    if coalesce_key and project_id is None:
        value = (payload or {}).get(coalesce_key)
        if value:
            running = await db.jobs.find_one(
                {
                    "type": job_type,
                    f"payload.{coalesce_key}": value,
                    "status": {"$in": ["queued", "running"]},
                }
            )
            if running:
                return running

    if job_type in EXCLUSIVE and project_id is not None:
        running = await db.jobs.find_one(
            {
                "projectId": project_id,
                "type": job_type,
                "status": {"$in": ["queued", "running"]},
            }
        )
        if running:
            if delay_seconds and running["status"] == "queued":
                # Still waiting: another file arrived, so give it time to land too.
                await db.jobs.update_one(
                    {"_id": running["_id"], "status": "queued"},
                    {"$set": {"nextAttemptAt": _due(delay_seconds)}},
                )
            return running

    job = {
        "type": job_type,
        "projectId": project_id,
        "payload": payload or {},
        "status": "queued",
        "attempts": 0,
        "error": None,
        "log": None,
        "createdBy": actor,
        "createdAt": datetime.now(timezone.utc),
        "startedAt": None,
        "finishedAt": None,
        "nextAttemptAt": _due(delay_seconds) if delay_seconds else None,
    }
    try:
        result = await db.jobs.insert_one(job)
    except DuplicateKeyError:
        existing = await db.jobs.find_one(
            {
                "projectId": project_id,
                "type": job_type,
                "status": {"$in": ["queued", "running"]},
            }
        )
        if existing:
            return existing
        raise
    job["_id"] = result.inserted_id

    await audit.record(
        action=f"job.enqueue.{job_type}",
        actor=actor,
        target={"projectId": project_id, "jobId": result.inserted_id},
    )
    return job


async def latest_for_project(project_id: ObjectId) -> dict[str, Any] | None:
    return await db.jobs.find_one({"projectId": project_id}, sort=[("createdAt", -1)])


async def active_for_project(project_id: ObjectId) -> dict[str, Any] | None:
    """Most recent queued or running job on this bid."""
    return await db.jobs.find_one(
        {"projectId": project_id, "status": {"$in": ["queued", "running"]}},
        sort=[("createdAt", -1)],
    )


async def active_count(project_id: ObjectId | None = None) -> int:
    query: dict[str, Any] = {"status": {"$in": ["queued", "running"]}}
    if project_id is not None:
        query["projectId"] = project_id
    return await db.jobs.count_documents(query)


async def metrics(window_hours: int = 24) -> dict[str, Any]:
    """Queue depth, throughput and failure rate, from MongoDB rather than logs.

    The only operational view of the queue was `docker logs`, which cannot answer
    "is it backed up" or "which job type is failing" without someone reading it.
    These are three aggregations over the collection that already holds the
    answer.

    Durations come from startedAt -> finishedAt, so a job still running does not
    drag the average down, and a job that was queued for an hour before a worker
    picked it up does not read as an hour of work.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    depth = {
        row["_id"]: row["count"]
        async for row in db.jobs.aggregate(
            [
                {"$match": {"status": {"$in": ["queued", "running"]}}},
                {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            ]
        )
    }

    by_type: dict[str, dict[str, Any]] = {}
    async for row in db.jobs.aggregate(
        [
            {"$match": {"createdAt": {"$gte": since}}},
            {
                "$group": {
                    "_id": {"type": "$type", "status": "$status"},
                    "count": {"$sum": 1},
                    "avgSeconds": {
                        "$avg": {
                            "$cond": [
                                {"$and": ["$startedAt", "$finishedAt"]},
                                {"$divide": [
                                    {"$subtract": ["$finishedAt", "$startedAt"]}, 1000
                                ]},
                                None,
                            ]
                        }
                    },
                }
            },
        ]
    ):
        entry = by_type.setdefault(
            row["_id"]["type"], {"total": 0, "done": 0, "failed": 0, "avgSeconds": None}
        )
        status = row["_id"]["status"]
        entry["total"] += row["count"]
        if status in ("done", "failed"):
            entry[status] += row["count"]
        if status == "done" and row.get("avgSeconds") is not None:
            entry["avgSeconds"] = round(row["avgSeconds"], 1)

    finished = sum(e["done"] + e["failed"] for e in by_type.values())
    failed = sum(e["failed"] for e in by_type.values())

    # The oldest thing still waiting is the number that says "backed up", and it
    # is the one a count of queued jobs cannot tell you.
    oldest = await db.jobs.find_one(
        {"status": "queued"}, {"createdAt": 1}, sort=[("createdAt", 1)]
    )

    return {
        "windowHours": window_hours,
        "queued": depth.get("queued", 0),
        "running": depth.get("running", 0),
        "oldestQueuedAt": oldest.get("createdAt") if oldest else None,
        "finished": finished,
        "failed": failed,
        # None rather than 0 when nothing finished: a 0% failure rate over zero
        # jobs is not good news, it is no news.
        "failureRate": round(failed / finished, 3) if finished else None,
        "byType": by_type,
    }
