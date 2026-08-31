"""Query-time routing over index.json and content.db."""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from cbc.documents import db as content_db
from cbc.documents import storage
from cbc.documents.versioning import get_current_version, resolve_document_folder


def _score(query: str, text: str) -> float:
    query = query.lower().strip()
    text = text.lower()
    if not query:
        return 0.0
    if query in text:
        return 1.0
    return SequenceMatcher(None, query, text).ratio()


def _load_index(folder: Path) -> list[dict[str, Any]]:
    path = folder / "index.json"
    if not path.exists():
        return []
    payload = storage.read_json(path)
    return payload if isinstance(payload, list) else []


def _resolve_folder(document_id: str | None, client_id: str | None, document_type: str | None) -> Path | None:
    if document_id:
        return resolve_document_folder(document_id)
    if client_id and document_type:
        current = get_current_version(client_id, document_type)
        if current:
            return resolve_document_folder(current)
    return None


def search_index(
    query: str,
    *,
    document_id: str | None = None,
    client_id: str | None = None,
    document_type: str | None = None,
    tag_filter: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    folder = _resolve_folder(document_id, client_id, document_type)
    if folder is None:
        return {"count": 0, "results": [], "note": "document not found or not indexed"}

    hits: list[dict[str, Any]] = []
    for entry in _load_index(folder):
        if tag_filter and tag_filter.lower() not in [
            t.lower() for t in entry.get("tags") or []
        ]:
            continue
        corpus = " ".join(
            [
                entry.get("section_title") or "",
                entry.get("description") or "",
                " ".join(entry.get("tags") or []),
                " ".join(entry.get("entities_present") or []),
            ]
        )
        score = _score(query, corpus)
        if score <= 0.1:
            continue
        hits.append(
            {
                "page_range": entry.get("page_range"),
                "section_title": entry.get("section_title"),
                "description": entry.get("description"),
                "tags": entry.get("tags"),
                "relevance_score": round(score, 3),
                "document_id": document_id or _manifest_id(folder),
            }
        )

    hits.sort(key=lambda h: h["relevance_score"], reverse=True)
    return {"count": len(hits[:limit]), "results": hits[:limit]}


def get_section_content(
    page_range: list[int],
    *,
    document_id: str | None = None,
    client_id: str | None = None,
    document_type: str | None = None,
) -> dict[str, Any]:
    folder = _resolve_folder(document_id, client_id, document_type)
    if folder is None:
        return {"found": False, "error": "document not found"}

    db_path = folder / "content.db"
    if not db_path.exists():
        return {"found": False, "error": "content.db missing"}

    start, end = int(page_range[0]), int(page_range[1])
    connection = content_db.connect(db_path, readonly=True)
    try:
        row = connection.execute(
            "SELECT page_start, page_end, section_title, raw_text, extracted_records, entities_present "
            "FROM sections WHERE page_start = ? AND page_end = ? LIMIT 1",
            [start, end],
        ).fetchone()
        if row is None:
            row = connection.execute(
                "SELECT page_start, page_end, section_title, raw_text, extracted_records, entities_present "
                "FROM sections WHERE page_start <= ? AND page_end >= ? "
                "ORDER BY (page_end - page_start) ASC LIMIT 1",
                [start, end],
            ).fetchone()
    finally:
        connection.close()

    if row is None:
        return {"found": False, "error": f"no section for page_range {page_range}"}

    return {
        "found": True,
        "document_id": document_id or _manifest_id(folder),
        "page_range": [row["page_start"], row["page_end"]],
        "section_title": row["section_title"],
        "raw_text": row["raw_text"],
        "extracted_records": json.loads(row["extracted_records"]),
        "entities_present": json.loads(row["entities_present"]),
    }


def get_exact_record(
    code: str,
    *,
    document_id: str | None = None,
    client_id: str | None = None,
    document_type: str | None = None,
) -> dict[str, Any]:
    folder = _resolve_folder(document_id, client_id, document_type)
    if folder is None:
        return {"found": False, "error": "document not found"}

    needle = str(code).strip().upper()
    for entry in _load_index(folder):
        entities = [str(e).strip().upper() for e in entry.get("entities_present") or []]
        if needle in entities or any(needle == e.split("-")[0] for e in entities):
            content = get_section_content(
                entry["page_range"],
                document_id=document_id or _manifest_id(folder),
            )
            if not content.get("found"):
                continue
            for record in content.get("extracted_records") or []:
                record_code = str(record.get("code") or record.get("part") or "").strip().upper()
                if record_code == needle or record_code.split("-")[0] == needle.split("-")[0]:
                    return {
                        "found": True,
                        "document_id": content["document_id"],
                        "page_range": content["page_range"],
                        "record": record,
                        "section_title": content.get("section_title"),
                    }
    return {"found": False, "code": code, "note": "exact code not in index"}


def list_document_versions(client_id: str, document_type: str) -> dict[str, Any]:
    from cbc.documents.versioning import list_versions

    versions = list_versions(client_id, document_type)
    current = get_current_version(client_id, document_type)
    return {
        "client_id": client_id,
        "document_type": document_type,
        "current_version": current,
        "count": len(versions),
        "versions": versions,
    }


def _manifest_id(folder: Path) -> str | None:
    manifest_path = folder / "manifest.json"
    if not manifest_path.exists():
        return None
    payload = storage.read_json(manifest_path)
    return payload.get("document_id")
