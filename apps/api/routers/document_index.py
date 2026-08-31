"""Document deep-index status and version listing."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from cbc.db import db, serialise
from cbc.documents import storage
from cbc.documents.search import list_document_versions as search_list_versions
from cbc.documents.versioning import resolve_document_folder

router = APIRouter(prefix="/api/document-index", tags=["document-index"])


@router.get("/{document_id}/status")
async def document_status(document_id: str) -> dict[str, Any]:
    record = await db.document_indexes.find_one({"documentId": document_id})
    if not record:
        raise HTTPException(404, "document index not found")

    manifest_summary: dict[str, Any] | None = None
    folder = resolve_document_folder(document_id)
    if folder and (folder / "manifest.json").exists():
        manifest_summary = storage.read_json(folder / "manifest.json")

    review_count = record.get("reviewNeededCount")
    if review_count is None and folder and (folder / "review_needed.json").exists():
        review = storage.read_json(folder / "review_needed.json")
        review_count = len(review) if isinstance(review, list) else 0

    return {
        "documentIndex": serialise(record),
        "progress": {
            "sectionsDone": record.get("sectionsDone", 0),
            "sectionsTotal": record.get("sectionsTotal", 0),
            "status": record.get("status", "unknown"),
        },
        "reviewNeededCount": review_count or 0,
        "manifest": manifest_summary,
        "ready": record.get("status") == "ready" and not (review_count or 0),
    }


@router.get("/versions")
async def list_versions(
    clientId: str = Query(...),
    documentType: str = Query(...),
) -> dict[str, Any]:
    return search_list_versions(clientId, documentType)
