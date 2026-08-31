"""End-to-end deep indexing pipeline (Steps A–D)."""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Callable

from cbc.core.llm import LLMClient
from cbc.documents import db as content_db
from cbc.documents import storage
from cbc.documents.completeness import reconcile_section
from cbc.documents.diff import generate_diff_report
from cbc.documents.extract import extract_pages
from cbc.documents.models import Manifest, ReviewItem, SchemaConfig, SectionIndexEntry
from cbc.documents.schema import discover_schema
from cbc.documents.section_extract import extract_section_records
from cbc.documents.sections import SectionChunk, split_into_sections
from cbc.documents.versioning import (
    get_current_version,
    promote_current_version,
    register_version,
    resolve_document_folder,
)

log = logging.getLogger("cbc.document_index")


class IndexingError(RuntimeError):
    pass


ProgressCallback = Callable[[int, int, str], None]


def index_document(
    source_path: Path,
    *,
    document_id: str,
    client_id: str,
    document_type: str,
    effective_date: str,
    llm: LLMClient | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    if not source_path.exists():
        raise IndexingError(f"source file missing: {source_path}")

    effective = storage.normalise_effective(effective_date)
    folder = storage.document_dir(client_id, document_type, effective, document_id)
    register_version(
        document_id=document_id,
        client_id=client_id,
        document_type=document_type,
        effective_date=effective,
        folder=folder,
        source_path=str(source_path),
    )

    storage.link_source_pdf(source_path, folder / "source.pdf")

    if progress:
        progress(0, 0, "extracting pages")
    pages = extract_pages(source_path)

    if progress:
        progress(0, 0, "discovering schema")
    schema = discover_schema(pages, llm, document_id=document_id)
    storage.write_json(folder / "schema_config.json", schema.model_dump())

    sections = split_into_sections(pages, schema)
    total = len(sections) or 1

    index_entries: list[SectionIndexEntry] = []
    review_items: list[ReviewItem] = []
    total_records = 0

    connection = content_db.initialise(folder / "content.db")
    try:
        connection.execute("DELETE FROM sections")
        for index, chunk in enumerate(sections):
            if progress:
                progress(index + 1, total, chunk.section_title)

            def extract_fn(text: str, page_range: list[int], title: str):
                return extract_section_records(
                    text, page_range, title, schema, llm, document_id=document_id
                )

            result, review = reconcile_section(
                raw_text=chunk.raw_text,
                page_range=chunk.page_range,
                section_title=chunk.section_title,
                schema=schema,
                extract_fn=extract_fn,
            )
            if result is None:
                continue
            if review:
                review_items.append(review)

            total_records += len(result.extracted_records)
            index_entries.append(
                SectionIndexEntry(
                    page_range=result.page_range,
                    section_title=result.section_title,
                    description=result.description,
                    tags=result.tags,
                    entities_present=result.entities_present,
                )
            )
            _persist_section(connection, chunk, result)
    finally:
        connection.close()

    storage.write_json(
        folder / "index.json",
        [entry.model_dump() for entry in index_entries],
    )
    storage.write_json(
        folder / "review_needed.json",
        [item.model_dump() for item in review_items],
    )

    manifest = Manifest(
        document_id=document_id,
        client_id=client_id,
        document_type=document_type,
        effective_date=effective,
        source_path=str(source_path),
        schema_config=schema,
        total_sections=len(index_entries),
        total_records=total_records,
        review_needed_count=len(review_items),
        indexing_completed_at=storage.now_iso(),
        status="review_needed" if review_items else "ready",
    )
    storage.write_json(folder / "manifest.json", manifest.model_dump())

    previous = get_current_version(client_id, document_type)
    promoted = promote_current_version(
        document_id,
        client_id,
        document_type,
        review_count=len(review_items),
    )
    if promoted and previous and previous != document_id:
        old_folder = resolve_document_folder(previous)
        if old_folder:
            generate_diff_report(
                old_folder,
                folder,
                from_document_id=previous,
                to_document_id=document_id,
                client_id=client_id,
                document_type=document_type,
            )

    return {
        "document_id": document_id,
        "folder": str(folder),
        "status": manifest.status,
        "total_sections": len(index_entries),
        "total_records": total_records,
        "review_needed_count": len(review_items),
        "promoted_current": promoted,
        "llm_calls": len(llm.audit_log) if llm else 0,
    }


def _persist_section(
    connection: sqlite3.Connection,
    chunk: SectionChunk,
    result,
) -> None:
    connection.execute(
        "INSERT INTO sections (page_start, page_end, section_title, raw_text, extracted_records, entities_present) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            result.page_range[0],
            result.page_range[1],
            result.section_title,
            chunk.raw_text,
            json.dumps(result.extracted_records),
            json.dumps(result.entities_present),
        ],
    )


def delete_document(document_id: str) -> dict[str, Any]:
    import shutil

    folder = resolve_document_folder(document_id)
    if folder is None:
        return {"removed": False, "document_id": document_id}
    shutil.rmtree(folder, ignore_errors=True)
    return {"removed": True, "document_id": document_id, "folder": str(folder)}
