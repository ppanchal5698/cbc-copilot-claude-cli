"""Bid documents - upload, list, serve, and the trigger that wakes Claude.

Uploading a building plan is the event the whole pipeline hangs off: the file
lands in `projects/{slug}/uploads/raw/`, a document row is written, and an
`extract_bid_set` job is enqueued for the worker to pick up.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from api.config import settings
from api.db import db, oid, serialise
from api.deps import Actor
from api.routers.projects import load
from api.routers.versions import snapshot
from api.services import audit, jobs, pdf, storage
from api.services.document_index import enqueue_index

router = APIRouter(prefix="/api/projects/{code}/documents", tags=["documents"])

PDF_MAGIC = b"%PDF-"

# How long an autopilot run waits after an upload, so several PDFs dropped
# together are read as one bid set rather than starting a run that misses them.
PIPELINE_DEBOUNCE_SECONDS = int(os.environ.get("PIPELINE_DEBOUNCE_SECONDS", "60"))


@router.get("")
async def list_documents(code: str) -> dict:
    project = await load(code)
    docs = await db.documents.find({"projectId": project["_id"]}).sort("uploadedAt", 1).to_list(200)
    return {"documents": serialise(docs)}


@router.post("", status_code=201)
async def upload_document(
    code: str,
    actor: Actor,
    file: UploadFile = File(...),
    kind: str = Form("plan"),
) -> dict:
    project = await load(code)

    storage.scaffold(project["slug"])
    target = storage.unique_filename(storage.raw_dir(project["slug"]), file.filename or "upload.pdf")
    try:
        size = await storage.receive_upload(
            file, target, settings.max_upload_bytes, magic=PDF_MAGIC
        )
    except ValueError as exc:
        raise HTTPException(413 if "exceeds" in str(exc) else 415, str(exc)) from exc

    # A bid set is a CAD export; counting its pages is real work, and doing it
    # inline blocked every other request - including the health check - for the
    # duration.
    try:
        pages = await asyncio.to_thread(pdf.page_count, target)
    except Exception:
        target.unlink(missing_ok=True)
        raise HTTPException(422, "could not read that PDF - it may be corrupt")

    document = {
        "projectId": project["_id"],
        "filename": target.name,
        "kind": kind,
        "pages": pages,
        "bytes": size,
        "path": storage.relative(target),
        "state": "received",
        "uploadedAt": datetime.now(timezone.utc),
        "uploadedBy": actor,
    }
    result = await db.documents.insert_one(document)
    document["_id"] = result.inserted_id

    # This is the notification to Claude Code.
    #
    # An addendum is different in kind: it revises a bid that may already be
    # priced, so the current state is frozen into a new version first and the
    # differences are flagged rather than merged (Matrix 4.1 is still open).
    version = None
    if kind == "addendum":
        version = await snapshot(project, f"Addendum: {target.name}", actor)
        job = await jobs.enqueue(
            "ingest_addendum",
            project_id=project["_id"],
            payload={
                "documentId": str(result.inserted_id),
                "filename": target.name,
                "version": version["version"],
            },
            actor=actor,
        )
    elif project.get("autopilot"):
        # Phase 0-6 in one session. Delayed a little so the rest of a multi-file
        # bid set lands first - the run reads the whole of uploads/raw/, and one
        # that started on this file alone would not see the others.
        job = await jobs.enqueue(
            "run_full_pipeline",
            project_id=project["_id"],
            payload={"documentId": str(result.inserted_id), "filename": target.name},
            actor=actor,
            delay_seconds=PIPELINE_DEBOUNCE_SECONDS,
        )
    else:
        job = await jobs.enqueue(
            "extract_bid_set",
            project_id=project["_id"],
            payload={"documentId": str(result.inserted_id), "filename": target.name},
            actor=actor,
        )

    document_index_id, deep_index_job = await enqueue_index(
        source_path=storage.relative(target),
        client_id=project["slug"],
        document_type=kind,
        effective_date=None,
        actor=actor,
        trigger="upload",
        project_id=str(project["_id"]),
    )
    await db.documents.update_one(
        {"_id": result.inserted_id},
        {"$set": {"documentIndexId": document_index_id}},
    )

    await audit.record(
        "document.upload",
        actor,
        {"projectId": project["_id"], "documentId": result.inserted_id},
        after={"kind": kind},
    )

    return {
        "document": serialise(document),
        "job": serialise(job),
        "deepIndexJob": serialise(deep_index_job),
        "documentIndexId": document_index_id,
        "autopilot": bool(project.get("autopilot")) and kind != "addendum",
        "version": version["version"] if version else None,
        "note": (
            "Prior work was snapshotted; differences will be flagged, not merged."
            if version
            else None
        ),
    }


@router.get("/{document_id}/file")
async def get_file(code: str, document_id: str) -> FileResponse:
    """Serve the raw PDF so the reviewer sees the actual drawing, not a re-rendering."""
    await load(code)
    document = await db.documents.find_one({"_id": oid(document_id)})
    if not document:
        raise HTTPException(404, "document not found")

    path = storage.absolute(document["path"])
    if not path.exists():
        raise HTTPException(410, f"file missing on disk: {document['path']}")

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=document["filename"],
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/{document_id}/page/{page_number}")
async def get_page(code: str, document_id: str, page_number: int, dpi: int = 110) -> Response:
    """A rendered page image, for viewers that cannot run pdf.js."""
    await load(code)
    document = await db.documents.find_one({"_id": oid(document_id)})
    if not document:
        raise HTTPException(404, "document not found")

    try:
        image = await asyncio.to_thread(
            pdf.render_page, storage.absolute(document["path"]), page_number, dpi
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return Response(
        await asyncio.to_thread(image.read_bytes),
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get("/{document_id}/page/{page_number}/size")
async def get_page_size(code: str, document_id: str, page_number: int) -> dict:
    """Page dimensions in PDF points - the frame every stored bbox is measured against."""
    await load(code)
    document = await db.documents.find_one({"_id": oid(document_id)})
    if not document:
        raise HTTPException(404, "document not found")
    return await asyncio.to_thread(
        pdf.page_size, storage.absolute(document["path"]), page_number
    )


@router.delete("/{document_id}", status_code=204)
async def delete_document(code: str, document_id: str, actor: Actor) -> None:
    """Detach a document from the bid. The file itself stays - raw uploads are immutable."""
    project = await load(code)
    document = await db.documents.find_one({"_id": oid(document_id)})
    if not document:
        raise HTTPException(404, "document not found")

    await db.documents.delete_one({"_id": document["_id"]})
    await audit.record(
        "document.delete",
        actor,
        {"projectId": project["_id"], "documentId": document["_id"]},
        before=document.get("filename"),
        note="file retained on disk",
    )
