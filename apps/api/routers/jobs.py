"""Job status - what the header pill and the run banner read."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from cbc.db import db, oid, serialise
from apps.api.deps import ADMIN_ROLES, Actor
from cbc.schemas import JobCreate
from cbc.schemas.common import ESTIMATOR_JOB_TYPES, EXCLUSIVE_JOB_TYPES
from apps.api.routers.projects import load
from apps.api.pipeline_jobs import enqueue_pipeline
from cbc.services import audit, jobs as job_service

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(
    project: str | None = None,
    status: str | None = None,
    limit: int = 25,
    pipeline_active: bool = False,
) -> dict:
    query: dict = {}
    project_doc = None
    if project:
        project_doc = await load(project)
        query["projectId"] = project_doc["_id"]
    if pipeline_active:
        if project_doc is None:
            raise HTTPException(400, "project is required when pipeline_active is set")
        active = await job_service.active_pipeline_job(project_doc["_id"])
        return {
            "jobs": serialise([active]) if active else [],
            "active": await job_service.active_count(),
        }
    if status:
        query["status"] = status

    found = await db.jobs.find(query).sort("createdAt", -1).to_list(min(limit, 100))
    return {"jobs": serialise(found), "active": await job_service.active_count()}


@router.get("/metrics")
async def job_metrics(hours: int = 24) -> dict:
    """Queue depth, throughput and failure rate.

    Declared before `/{job_id}`: FastAPI matches in declaration order, so the
    other way round this route is a job whose id is the word "metrics".
    """
    return serialise(await job_service.metrics(max(1, min(hours, 24 * 30))))


@router.get("/{job_id}")
async def get_job(job_id: str) -> dict:
    job = await db.jobs.find_one({"_id": oid(job_id)})
    if not job:
        raise HTTPException(404, "job not found")
    return serialise(job)


@router.post("", status_code=201)
async def create_job(body: JobCreate, actor: Actor) -> dict:
    if body.type not in ESTIMATOR_JOB_TYPES:
        await _require_admin(actor, body.type)
    project_id = None
    if body.projectId:
        project_id = (await load(body.projectId))["_id"]
    if project_id is not None and body.type in job_service.EXCLUSIVE:
        job = await enqueue_pipeline(
            body.type, project_id, payload=body.payload, actor=actor
        )
    else:
        job = await job_service.enqueue(body.type, project_id, body.payload, actor)
    return serialise(job)


async def _require_admin(actor: str, job_type: str) -> None:
    user = await db.users.find_one({"email": actor.lower()}, {"role": 1})
    if not user or user.get("role") not in ADMIN_ROLES:
        raise HTTPException(
            403,
            f"{actor} is not permitted to enqueue {job_type!r}. "
            "Catalog and price-book jobs need an administrator.",
        )


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, actor: Actor) -> dict:
    job = await db.jobs.find_one({"_id": oid(job_id)})
    if not job:
        raise HTTPException(404, "job not found")
    if job["status"] not in ("queued", "running"):
        raise HTTPException(409, f"job is already {job['status']}")

    await db.jobs.update_one(
        {"_id": job["_id"]},
        {
            "$set": {
                "status": "cancelled",
                "cancelledAt": datetime.now(timezone.utc),
                "cancelledBy": actor,
            }
        },
    )
    await audit.record(
        "job.cancel",
        actor,
        {"jobId": job["_id"], "projectId": job.get("projectId")},
    )
    return serialise(await db.jobs.find_one({"_id": job["_id"]}))
