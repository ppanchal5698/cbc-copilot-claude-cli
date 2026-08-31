"""Document deep-index jobs — local LLM pipeline, not a Claude Code pass."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.config import settings
from api.db import db
from api.services import provider
from cbc_core.llm import LLMClient
from document_index import pipeline, storage
from document_index.pipeline import IndexingError

log = logging.getLogger("cbc.worker.document_index")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _update_status(document_id: str, fields: dict[str, Any]) -> None:
    await db.document_indexes.update_one(
        {"documentId": document_id},
        {"$set": {**fields, "updatedAt": _now()}},
        upsert=True,
    )


def _index_sync(
    path: Path,
    document_id: str,
    client_id: str,
    document_type: str,
    effective_date: str,
    llm: LLMClient | None,
) -> dict[str, Any]:
    def progress(done: int, total: int, label: str) -> None:
        # Progress is written from the worker thread via asyncio — skip sync Mongo here;
        # the handler updates status after completion.
        log.info("index_document %s: %s/%s %s", document_id, done, total, label)

    return pipeline.index_document(
        path,
        document_id=document_id,
        client_id=client_id,
        document_type=document_type,
        effective_date=effective_date,
        llm=llm,
        progress=progress,
    )


async def index_document(job: dict[str, Any]) -> str:
    payload = job.get("payload") or {}
    document_id = payload.get("documentId")
    source_path = payload.get("sourcePath")
    client_id = payload.get("clientId")
    document_type = payload.get("documentType")
    effective_date = payload.get("effectiveDate")

    if not all([document_id, source_path, client_id, document_type]):
        raise ValueError(
            "index_document requires payload.documentId, sourcePath, clientId, documentType"
        )

    from api.services import storage as file_storage

    path = file_storage.absolute(source_path)
    if not path.exists():
        raise FileNotFoundError(f"source file missing: {source_path}")

    await _update_status(
        document_id,
        {
            "documentId": document_id,
            "clientId": client_id,
            "documentType": document_type,
            "effectiveDate": storage.normalise_effective(effective_date),
            "sourcePath": source_path,
            "status": "processing",
            "sectionsDone": 0,
            "sectionsTotal": 0,
            "priceBookId": payload.get("priceBookId"),
            "projectId": payload.get("projectId"),
            "trigger": payload.get("trigger"),
        },
    )

    config = await db.settings.find_one({"_id": "claude"}) or provider.default_config()
    env, _ = provider.build_env(config)
    llm: LLMClient | None
    try:
        llm = LLMClient.from_env(env)
    except RuntimeError:
        log.warning("no LLM credentials — indexing with heuristic extraction only")
        llm = None

    report = await asyncio.to_thread(
        _index_sync,
        path,
        document_id,
        client_id,
        document_type,
        storage.normalise_effective(effective_date),
        llm,
    )

    await _update_status(
        document_id,
        {
            "status": report["status"],
            "sectionsTotal": report["total_sections"],
            "sectionsDone": report["total_sections"],
            "totalRecords": report["total_records"],
            "reviewNeededCount": report["review_needed_count"],
            "folder": report["folder"],
            "promotedCurrent": report["promoted_current"],
            "indexingCompletedAt": _now(),
        },
    )

    if payload.get("priceBookId"):
        from api.db import oid

        await db.price_books.update_one(
            {"_id": oid(payload["priceBookId"])},
            {
                "$set": {
                    "documentIndexId": document_id,
                    "documentIndexStatus": report["status"],
                    "updatedAt": _now(),
                }
            },
        )

    review_note = (
        f", {report['review_needed_count']} section(s) need review"
        if report["review_needed_count"]
        else ""
    )
    return (
        f"deep-indexed {report['total_records']} record(s) in "
        f"{report['total_sections']} section(s){review_note}"
    )


async def delete_document(job: dict[str, Any]) -> str:
    payload = job.get("payload") or {}
    document_id = payload.get("documentId")
    if not document_id:
        raise ValueError("delete_document requires payload.documentId")

    report = await asyncio.to_thread(pipeline.delete_document, document_id)
    await db.document_indexes.delete_one({"documentId": document_id})
    if report.get("removed"):
        return f"removed deep index {document_id}"
    return f"no deep index found for {document_id}"
