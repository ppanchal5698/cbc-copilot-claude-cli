"""Job status - what the header pill and the run banner read."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.db import db, oid, serialise
from api.models import JobCreate
from api.routers.projects import load
from api.services import jobs as job_service

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(project: str | None = None, status: str | None = None, limit: int = 25) -> dict:
    query: dict = {}
    if project:
        query["projectId"] = (await load(project))["_id"]
    if status:
        query["status"] = status

    found = await db.jobs.find(query).sort("createdAt", -1).to_list(min(limit, 100))
    return {"jobs": serialise(found), "active": await job_service.active_count()}


@router.get("/{job_id}")
async def get_job(job_id: str) -> dict:
    job = await db.jobs.find_one({"_id": oid(job_id)})
    if not job:
        raise HTTPException(404, "job not found")
    return serialise(job)


@router.post("", status_code=201)
async def create_job(body: JobCreate, actor: str = "estimator") -> dict:
    project_id = None
    if body.projectId:
        project_id = (await load(body.projectId))["_id"]
    job = await job_service.enqueue(body.type, project_id, body.payload, actor)
    return serialise(job)


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, actor: str = "estimator") -> dict:
    job = await db.jobs.find_one({"_id": oid(job_id)})
    if not job:
        raise HTTPException(404, "job not found")
    if job["status"] not in ("queued", "running"):
        raise HTTPException(409, f"job is already {job['status']}")

    await db.jobs.update_one({"_id": job["_id"]}, {"$set": {"status": "cancelled"}})
    return serialise(await db.jobs.find_one({"_id": job["_id"]}))
