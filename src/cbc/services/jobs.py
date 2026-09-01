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
