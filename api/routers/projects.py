"""Projects - the bid record every other screen hangs off."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.db import db, oid, serialise
from api.models import ProjectCreate, ProjectUpdate
from api.services import audit, jobs, storage

router = APIRouter(prefix="/api/projects", tags=["projects"])

STAGE_PROGRESS = {"intake": 0, "extraction": 33, "quote": 67, "proposal": 100}


async def load(code_or_id: str) -> dict[str, Any]:
    """Look a project up by code (CBC-260143), slug, or id - whatever the caller has."""
    query: dict[str, Any] = {"$or": [{"code": code_or_id}, {"slug": code_or_id}]}
    try:
        query["$or"].append({"_id": oid(code_or_id)})
    except ValueError:
        pass
    project = await db.projects.find_one(query)
    if not project:
        raise HTTPException(404, f"project not found: {code_or_id}")
    return project


async def _decorate(project: dict[str, Any]) -> dict[str, Any]:
    """Attach the counts the board and stage bar render."""
    project_id = project["_id"]
    statuses = await db.line_items.aggregate(
        [{"$match": {"projectId": project_id}}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]
    ).to_list(length=20)
    counts = {row["_id"]: row["n"] for row in statuses}
    quote = await db.quotes.find_one({"projectId": project_id})
    latest = await jobs.latest_for_project(project_id)

    # `status` carries provenance (`by_hand`) in the same field as review state,
    # so a confirmed hand-added line is not in the `clear` bucket. Confirmation is
    # what "cleared" means to an estimator, so count the thing that records it.
    confirmed = await db.line_items.count_documents(
        {"projectId": project_id, "confirmedAt": {"$ne": None}}
    )

    return {
        **serialise(project),
        "counts": {
            "total": sum(counts.values()),
            "clear": confirmed,
            "needsLook": counts.get("needs_look", 0),
            "duplicate": counts.get("duplicate", 0),
            "byHand": counts.get("by_hand", 0),
        },
        "documentCount": await db.documents.count_documents({"projectId": project_id}),
        "version": project.get("version", 1),
        "callCount": await db.calls.count_documents({"projectId": project_id}),
        "quoteTotal": (quote or {}).get("grandTotal"),
        "activeJob": serialise(latest) if latest and latest["status"] in ("queued", "running") else None,
    }


@router.get("")
async def list_projects(
    stage: str | None = None,
    q: str | None = None,
    limit: int = Query(default=50, le=200),
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if stage:
        query["stage"] = stage
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"code": {"$regex": q, "$options": "i"}},
            {"gc": {"$regex": q, "$options": "i"}},
            {"brand": {"$regex": q, "$options": "i"}},
        ]

    projects = await db.projects.find(query).sort("createdAt", -1).to_list(length=limit)
    return {"projects": [await _decorate(p) for p in projects]}


@router.post("", status_code=201)
async def create_project(body: ProjectCreate, actor: str = "estimator") -> dict[str, Any]:
    codes = await db.projects.distinct("code")
    code = storage.next_project_code(codes)

    slug = storage.slugify(body.name)
    if await db.projects.find_one({"slug": slug}):
        slug = f"{slug}_{code.lower().replace('-', '_')}"

    now = datetime.now(timezone.utc)
    doc = {
        **body.model_dump(exclude_none=True),
        "bidDue": datetime.combine(body.bidDue, datetime.min.time(), tzinfo=timezone.utc)
        if body.bidDue
        else None,
        "code": code,
        "slug": slug,
        "stage": "intake",
        "progress": 0,
        "createdAt": now,
        "updatedAt": now,
    }
    result = await db.projects.insert_one(doc)
    doc["_id"] = result.inserted_id

    storage.scaffold(slug)
    await audit.record("project.create", actor, {"projectId": result.inserted_id}, after=code)
    return await _decorate(doc)


@router.get("/{code}")
async def get_project(code: str) -> dict[str, Any]:
    return await _decorate(await load(code))


@router.patch("/{code}")
async def update_project(code: str, body: ProjectUpdate, actor: str = "estimator") -> dict:
    project = await load(code)
    changes = body.model_dump(exclude_none=True)
    if not changes:
        return await _decorate(project)

    if "bidDue" in changes and changes["bidDue"]:
        changes["bidDue"] = datetime.combine(
            changes["bidDue"], datetime.min.time(), tzinfo=timezone.utc
        )
    if "stage" in changes:
        changes["progress"] = STAGE_PROGRESS.get(changes["stage"], project.get("progress", 0))
    changes["updatedAt"] = datetime.now(timezone.utc)

    await db.projects.update_one({"_id": project["_id"]}, {"$set": changes})
    await audit.record(
        "project.update",
        actor,
        {"projectId": project["_id"]},
        before={k: project.get(k) for k in changes},
        after=changes,
    )
    return await _decorate(await db.projects.find_one({"_id": project["_id"]}))


@router.delete("/{code}", status_code=204)
async def delete_project(code: str, actor: str = "estimator") -> None:
    """Remove the bid record. Uploaded documents stay on disk deliberately.

    Raw uploads are immutable evidence (file-safety rule); deleting a database
    row must not quietly destroy the drawings a quote was built from.
    """
    project = await load(code)
    project_id = project["_id"]
    for collection in (db.line_items, db.quote_lines, db.quotes, db.proposals, db.documents):
        await collection.delete_many({"projectId": project_id})
    await db.projects.delete_one({"_id": project_id})
    await audit.record(
        "project.delete",
        actor,
        {"projectId": project_id},
        before=project.get("code"),
        note="files retained on disk",
    )
