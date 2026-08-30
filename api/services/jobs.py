"""Job queue - how the estimator's actions reach Claude Code.

The API enqueues; the worker in `worker/` claims and runs. Nothing here spawns a
process: extraction on a 30-page CAD set is minutes of work, far longer than a
web request should hold open, and a dropped connection must not lose the job.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from api.db import db
from api.schemas.common import EXCLUSIVE_JOB_TYPES
from api.services import audit

EXCLUSIVE = set(EXCLUSIVE_JOB_TYPES)


async def enqueue(
    job_type: str,
    project_id: ObjectId | None = None,
    payload: dict[str, Any] | None = None,
    actor: str = "estimator",
) -> dict[str, Any]:
    if job_type in EXCLUSIVE and project_id is not None:
        running = await db.jobs.find_one(
            {
                "projectId": project_id,
                "type": job_type,
                "status": {"$in": ["queued", "running"]},
            }
        )
        if running:
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
