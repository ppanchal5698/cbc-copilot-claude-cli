"""Job queue - how the estimator's actions reach Claude Code.

The API enqueues; the worker in `worker/` claims and runs. Nothing here spawns a
process: extraction on a 30-page CAD set is minutes of work, far longer than a
web request should hold open, and a dropped connection must not lose the job.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from api.db import db
from api.services import audit

# One in-flight job of the same type per project. A second "re-run extraction"
# click while the first is still running is a double-click, not a second job.
EXCLUSIVE = {"extract_bid_set", "rerun_extraction", "match_and_price", "build_proposal"}


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
    result = await db.jobs.insert_one(job)
    job["_id"] = result.inserted_id

    await audit.record(
        action=f"job.enqueue.{job_type}",
        actor=actor,
        target={"projectId": project_id, "jobId": result.inserted_id},
    )
    return job


async def latest_for_project(project_id: ObjectId) -> dict[str, Any] | None:
    return await db.jobs.find_one({"projectId": project_id}, sort=[("createdAt", -1)])


async def active_count(project_id: ObjectId | None = None) -> int:
    query: dict[str, Any] = {"status": {"$in": ["queued", "running"]}}
    if project_id is not None:
        query["projectId"] = project_id
    return await db.jobs.count_documents(query)
