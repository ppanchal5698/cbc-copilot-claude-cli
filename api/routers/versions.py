"""Alternates and addenda - the interim structure only.

CBC has not answered how alternates are quoted or how addenda reconcile
(Matrix 4.1 / FR-14 / Open Item 11). What the workbook *does* record is the
interim rule, and that is all this module implements:

  - the base bid and each alternate are distinct, comparable line groups
  - an addendum never overwrites prior work

So an addendum snapshots the current state into a new version and the differences
are flagged for the estimator. Nothing is auto-merged, because the rule for
merging has not been agreed. Every response says so.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from api.db import db, oid, serialise
from api.models import AlternateCreate, VersionCreate
from api.routers.projects import load
from api.services import audit, jobs, pricing

router = APIRouter(prefix="/api/projects/{code}", tags=["versions"])

PENDING_NOTE = (
    "How an addendum reconciles against the previous version, and whether an "
    "alternate inherits the base bid's confirmations, are still open questions "
    "(Matrix 4.1 / Open Item 11). Differences are flagged, never merged."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── alternates ──────────────────────────────────────────────────────────────


@router.get("/alternates")
async def list_alternates(code: str) -> dict[str, Any]:
    """Every line group on this bid, with its own independent total.

    The base bid is `alternateGroup: null`. Totals are per group so the estimator
    can compare them side by side, which is the whole point of an alternate.
    """
    project = await load(code)
    project_id = project["_id"]

    # Declared alternates live on the project so an empty one still shows up;
    # anything a line points at is included too, so data can never orphan a group.
    names = list(project.get("alternates") or [])
    names += await db.line_items.distinct("alternateGroup", {"projectId": project_id})
    names += await db.quote_lines.distinct("alternateGroup", {"projectId": project_id})
    groups = [None] + sorted({n for n in names if n})

    quote = await db.quotes.find_one({"projectId": project_id}) or {}
    state = quote.get("taxJurisdiction") or project.get("state")

    out = []
    for group in groups:
        query = {"projectId": project_id, "alternateGroup": group}
        lines = await db.quote_lines.find(query).to_list(2000)
        totals = pricing.totals(lines, state, quote.get("freight") if group is None else None)
        out.append(
            {
                "name": group,
                "label": group or "Base bid",
                "isBase": group is None,
                "lineItemCount": await db.line_items.count_documents(query),
                "quoteLineCount": len(lines),
                "subtotal": totals["subtotal"],
                "grandTotal": totals["grandTotal"],
                "unpricedLines": totals["unpricedLines"],
            }
        )

    return {"alternates": out, "pending": PENDING_NOTE}


@router.post("/alternates", status_code=201)
async def create_alternate(code: str, body: AlternateCreate, actor: str = "estimator") -> dict:
    """Create an empty alternate group. Lines are moved into it deliberately.

    It does not copy the base bid: whether an alternate inherits the base is one
    of the unanswered questions, and copying would be inventing the answer.
    """
    project = await load(code)
    name = body.name.strip()

    if name in (project.get("alternates") or []):
        raise HTTPException(409, f"{name} already exists on this bid")

    await db.projects.update_one(
        {"_id": project["_id"]},
        {"$addToSet": {"alternates": name}, "$set": {"updatedAt": _now()}},
    )
    await audit.record("alternate.create", actor, {"projectId": project["_id"]}, after=name)
    return {
        "name": name,
        "label": name,
        "isBase": False,
        "lineItemCount": 0,
        "quoteLineCount": 0,
        "note": "Empty. Move lines into it, or add them by hand. " + PENDING_NOTE,
    }


@router.post("/alternates/assign")
async def assign_to_alternate(
    code: str,
    ids: list[str],
    alternate: str | None = None,
    scope: str = "line-items",
    actor: str = "estimator",
) -> dict:
    """Move lines between the base bid and an alternate."""
    project = await load(code)
    collection = db.line_items if scope == "line-items" else db.quote_lines
    if scope not in ("line-items", "quote-lines"):
        raise HTTPException(400, "scope must be 'line-items' or 'quote-lines'")

    result = await collection.update_many(
        {"_id": {"$in": [oid(i) for i in ids]}, "projectId": project["_id"]},
        {"$set": {"alternateGroup": alternate, "updatedAt": _now()}},
    )
    await audit.record(
        "alternate.assign",
        actor,
        {"projectId": project["_id"]},
        after={"alternate": alternate, "moved": result.modified_count, "scope": scope},
    )
    return {"moved": result.modified_count, "alternate": alternate}


# ── versions ────────────────────────────────────────────────────────────────


async def snapshot(project: dict[str, Any], reason: str, actor: str) -> dict[str, Any]:
    """Freeze the current line items and quote lines into a new version.

    This is what makes "an addendum never overwrites prior work" true rather than
    aspirational - the previous state is stored whole, not diffed.
    """
    project_id = project["_id"]
    latest = await db.versions.find_one({"projectId": project_id}, sort=[("version", -1)])
    number = (latest or {}).get("version", 0) + 1

    line_items = await db.line_items.find({"projectId": project_id}).to_list(5000)
    quote_lines = await db.quote_lines.find({"projectId": project_id}).to_list(5000)

    document = {
        "projectId": project_id,
        "version": number,
        "reason": reason,
        "createdAt": _now(),
        "createdBy": actor,
        "reconciled": False,
        "lineItemCount": len(line_items),
        "quoteLineCount": len(quote_lines),
        "snapshot": {
            "lineItems": serialise(line_items),
            "quoteLines": serialise(quote_lines),
        },
    }
    result = await db.versions.insert_one(document)
    document["_id"] = result.inserted_id

    await db.projects.update_one({"_id": project_id}, {"$set": {"version": number}})
    await audit.record(
        "version.snapshot",
        actor,
        {"projectId": project_id, "versionId": result.inserted_id},
        after={"version": number, "reason": reason},
    )
    return document


@router.get("/versions")
async def list_versions(code: str) -> dict[str, Any]:
    project = await load(code)
    found = (
        await db.versions.find({"projectId": project["_id"]}, {"snapshot": 0})
        .sort("version", -1)
        .to_list(50)
    )
    unreconciled = sum(1 for v in found if not v.get("reconciled"))
    return {
        "versions": serialise(found),
        "current": project.get("version", 1),
        "unreconciled": unreconciled,
        "pending": PENDING_NOTE,
    }


@router.get("/versions/{version}")
async def get_version(code: str, version: int) -> dict[str, Any]:
    project = await load(code)
    found = await db.versions.find_one({"projectId": project["_id"], "version": version})
    if not found:
        raise HTTPException(404, f"version {version} not found")
    return serialise(found)


@router.post("/versions", status_code=201)
async def create_version(code: str, body: VersionCreate, actor: str = "estimator") -> dict:
    """Snapshot the current state, then ask Claude to read the addendum into it."""
    project = await load(code)
    document = await snapshot(project, body.reason, actor)

    job = None
    if body.documentId:
        job = await jobs.enqueue(
            "ingest_addendum",
            project_id=project["_id"],
            payload={
                "documentId": body.documentId,
                "version": document["version"],
                "reason": body.reason,
            },
            actor=actor,
        )

    return {
        "version": serialise({k: v for k, v in document.items() if k != "snapshot"}),
        "job": serialise(job) if job else None,
        "pending": PENDING_NOTE,
    }


@router.get("/versions/{version}/diff")
async def diff_version(code: str, version: int) -> dict[str, Any]:
    """What changed since a snapshot, by mark. Reported, never applied."""
    project = await load(code)
    stored = await db.versions.find_one({"projectId": project["_id"], "version": version})
    if not stored:
        raise HTTPException(404, f"version {version} not found")

    def key(item: dict[str, Any]) -> str:
        return str(item.get("mark") or item.get("description", ""))[:60]

    before = {key(i): i for i in stored["snapshot"]["lineItems"]}
    current = {
        key(i): i for i in await db.line_items.find({"projectId": project["_id"]}).to_list(5000)
    }

    watched = ("description", "size", "qty", "hwSet", "finish", "fireRating", "handing")
    changed = []
    for mark, now in current.items():
        was = before.get(mark)
        if not was:
            continue
        fields = [f for f in watched if str(was.get(f)) != str(now.get(f))]
        if fields:
            changed.append(
                {
                    "mark": mark,
                    "fields": fields,
                    "before": {f: was.get(f) for f in fields},
                    "after": {f: now.get(f) for f in fields},
                }
            )

    return {
        "version": version,
        "added": sorted(set(current) - set(before)),
        "removed": sorted(set(before) - set(current)),
        "changed": changed,
        "pending": PENDING_NOTE,
    }


@router.post("/versions/{version}/reconcile")
async def mark_reconciled(code: str, version: int, actor: str = "estimator") -> dict:
    """The estimator has worked through the differences. Records only their say-so."""
    project = await load(code)
    result = await db.versions.update_one(
        {"projectId": project["_id"], "version": version},
        {"$set": {"reconciled": True, "reconciledBy": actor, "reconciledAt": _now()}},
    )
    if not result.matched_count:
        raise HTTPException(404, f"version {version} not found")

    await audit.record(
        "version.reconciled", actor, {"projectId": project["_id"]}, after={"version": version}
    )
    return {"version": version, "reconciled": True, "by": actor}
