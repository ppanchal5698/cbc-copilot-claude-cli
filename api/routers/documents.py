"""Bid documents - upload, list, serve, and the trigger that wakes Claude.

Uploading a building plan is the event the whole pipeline hangs off: the file
lands in `projects/{slug}/uploads/raw/`, a document row is written, and an
`extract_bid_set` job is enqueued for the worker to pick up.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from api.config import settings
from api.db import db, oid, serialise
from api.routers.projects import load
from api.services import audit, jobs, pdf, storage

router = APIRouter(prefix="/api/projects/{code}/documents", tags=["documents"])

PDF_MAGIC = b"%PDF-"


@router.get("")
async def list_documents(code: str) -> dict:
    project = await load(code)
    docs = await db.documents.find({"projectId": project["_id"]}).sort("uploadedAt", 1).to_list(200)
    return {"documents": serialise(docs)}


@router.post("", status_code=201)
async def upload_document(
    code: str,
    file: UploadFile = File(...),
    kind: str = Form("plan"),
    actor: str = Form("estimator"),
) -> dict:
    project = await load(code)
    payload = await file.read()

    if len(payload) > settings.max_upload_bytes:
        raise HTTPException(413, f"file exceeds {settings.max_upload_mb} MB")
    if not payload.startswith(PDF_MAGIC):
        raise HTTPException(415, "only PDF bid documents are accepted")

    storage.scaffold(project["slug"])
    target = storage.unique_filename(storage.raw_dir(project["slug"]), file.filename or "upload.pdf")
    target.write_bytes(payload)

    try:
        pages = pdf.page_count(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise HTTPException(422, "could not read that PDF - it may be corrupt")

    document = {
        "projectId": project["_id"],
        "filename": target.name,
        "kind": kind,
        "pages": pages,
        "bytes": len(payload),
        "path": storage.relative(target),
        "state": "received",
        "uploadedAt": datetime.now(timezone.utc),
        "uploadedBy": actor,
    }
    result = await db.documents.insert_one(document)
    document["_id"] = result.inserted_id

    # This is the notification to Claude Code.
    job = await jobs.enqueue(
        "extract_bid_set",
        project_id=project["_id"],
        payload={"documentId": str(result.inserted_id), "filename": target.name},
        actor=actor,
    )
    await audit.record(
        "document.upload", actor, {"projectId": project["_id"], "documentId": result.inserted_id}
    )

    return {"document": serialise(document), "job": serialise(job)}


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
        image = pdf.render_page(storage.absolute(document["path"]), page_number, dpi)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return Response(
        image.read_bytes(),
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
    return pdf.page_size(storage.absolute(document["path"]), page_number)


@router.delete("/{document_id}", status_code=204)
async def delete_document(code: str, document_id: str, actor: str = "estimator") -> None:
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
