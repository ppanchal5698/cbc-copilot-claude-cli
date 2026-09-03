"""Job queue - how the estimator's actions reach Claude Code.

The API enqueues; the worker in `worker/` claims and runs. Nothing here spawns a
process: extraction on a 30-page CAD set is minutes of work, far longer than a
web request should hold open, and a dropped connection must not lose the job.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from cbc.db import db
from cbc.schemas.common import EXCLUSIVE_JOB_TYPES
from cbc.services import audit

EXCLUSIVE = set(EXCLUSIVE_JOB_TYPES)


class PipelineJobActive(Exception):
    """Another pipeline job is already queued or running on this bid."""

    def __init__(self, active: dict[str, Any]) -> None:
        self.active = active
        super().__init__(active.get("type", "pipeline"))


def _due(delay_seconds: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)


# Project-less job types, and the payload field that identifies the same work.
# Indexing is idempotent on the file hash, so a second pass over an unchanged
# sheet is pure waste - and two at once are a write race. Filename is the
# fallback for jobs enqueued before fileSha existed.
COALESCE_BY_PAYLOAD = {"index_catalog": "fileSha"}
COALESCE_FALLBACK = {"index_catalog": "filename"}


def _idempotency_key(
    job_type: str, project_id: ObjectId | None, payload: dict[str, Any] | None
) -> str:
    blob = json.dumps(
        {
            "type": job_type,
            "projectId": str(project_id) if project_id else "",
            "payload": payload or {},
        },
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _coalesce_lookup(
    job_type: str, payload: dict[str, Any] | None
) -> tuple[str, Any] | None:
    payload = payload or {}
    primary = COALESCE_BY_PAYLOAD.get(job_type)
    if primary and payload.get(primary):
        return f"payload.{primary}", payload[primary]
    fallback = COALESCE_FALLBACK.get(job_type)
    if fallback and payload.get(fallback):
        return f"payload.{fallback}", payload[fallback]
    return None


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
    coalesce = _coalesce_lookup(job_type, payload)
    if coalesce and project_id is None:
        field, value = coalesce
        running = await db.jobs.find_one(
            {
                "type": job_type,
                field: value,
                "status": {"$in": ["queued", "running"]},
            }
        )
        if running:
            return running

    if job_type in EXCLUSIVE and project_id is not None:
        running = await active_pipeline_job(project_id)
        if running:
            # Deliberately permissive: this returns whatever pipeline job is
            # already active, of any type, and `test_only_one_active_pipeline_job_
            # _per_project` pins that. `enqueue_exclusive` is the strict variant
            # that raises PipelineJobActive instead, and every API route that can
            # be given a mismatched type goes through it.
            if running["type"] == job_type and delay_seconds and running["status"] == "queued":
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
        "idempotencyKey": _idempotency_key(job_type, project_id, payload),
    }
    try:
        result = await db.jobs.insert_one(job)
    except DuplicateKeyError:
        if project_id is not None:
            existing = await active_pipeline_job(project_id)
            if existing:
                return existing
        existing = await db.jobs.find_one(
            {
                "idempotencyKey": job["idempotencyKey"],
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


async def active_pipeline_job(project_id: ObjectId) -> dict[str, Any] | None:
    """Newest queued or running pipeline job on this bid (one session per bid)."""
    return await db.jobs.find_one(
        {
            "projectId": project_id,
            "type": {"$in": list(EXCLUSIVE_JOB_TYPES)},
            "status": {"$in": ["queued", "running"]},
        },
        sort=[("createdAt", -1)],
    )


async def enqueue_exclusive(
    job_type: str,
    project_id: ObjectId,
    payload: dict[str, Any] | None = None,
    actor: str = "estimator",
    delay_seconds: int = 0,
) -> dict[str, Any]:
    """Queue a pipeline job unless another pipeline type is already active."""
    active = await active_pipeline_job(project_id)
    if active and active["type"] != job_type:
        raise PipelineJobActive(active)
    return await enqueue(job_type, project_id, payload, actor, delay_seconds)


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
