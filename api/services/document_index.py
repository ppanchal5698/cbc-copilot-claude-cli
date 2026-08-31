"""Helpers for enqueueing and inspecting document deep indexes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.config import settings
from api.db import db
from api.services import jobs
from document_index import storage as index_storage


def inventory_kind(filename: str) -> str | None:
    """Look up kind from pricebooks/index.json when present."""
    manifest = settings.pricebook_dir / "index.json"
    if not manifest.exists():
        return None
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    for entry in payload.get("pricebooks") or []:
        if entry.get("file") == filename:
            return entry.get("kind")
    return None


async def enqueue_index(
    *,
    source_path: str,
    client_id: str,
    document_type: str,
    effective_date: str | None = None,
    actor: str,
    trigger: str = "upload",
    price_book_id: str | None = None,
    project_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Queue index_document and create the Mongo metadata row."""
    document_id = index_storage.allocate_document_id()
    from datetime import datetime, timezone

    await db.document_indexes.insert_one(
        {
            "documentId": document_id,
            "clientId": client_id,
            "documentType": document_type,
            "effectiveDate": index_storage.normalise_effective(effective_date),
            "sourcePath": source_path,
            "status": "queued",
            "trigger": trigger,
            "priceBookId": price_book_id,
            "projectId": project_id,
            "createdAt": datetime.now(timezone.utc),
        }
    )
    job = await jobs.enqueue(
        "index_document",
        project_id=None,
        payload={
            "documentId": document_id,
            "sourcePath": source_path,
            "clientId": client_id,
            "documentType": document_type,
            "effectiveDate": index_storage.normalise_effective(effective_date),
            "trigger": trigger,
            "priceBookId": price_book_id,
            "projectId": project_id,
        },
        actor=actor,
    )
    return document_id, job


def should_deep_index_pricebook(filename: str, book: dict[str, Any] | None = None) -> bool:
    kind = (book or {}).get("kind") or inventory_kind(filename)
    if kind == "multiplier_sheet":
        return True
    return bool((book or {}).get("deepIndex"))
