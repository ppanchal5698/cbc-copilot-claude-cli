"""What a take-off pass wrote, into the database."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from pymongo import InsertOne, UpdateOne

from cbc.db import db
from cbc.services import storage
from cbc.services.sync_phases._common import (
    _distinct_keys,
    _identity,
    _normalize_schedule_payload,
    _now,
    _read_json,
    _status_for,
    door_number,
)

log = logging.getLogger("cbc.services.sync")


async def import_extraction(project: dict[str, Any]) -> dict[str, int]:
    """Load `extracted/door_schedule.json` into `lineItems`.

    Returns counts so the caller can report what a job actually changed.
    """
    slug, project_id = project["slug"], project["_id"]
    raw = _read_json(storage.project_dir(slug) / "extracted" / "door_schedule.json")
    source = storage.project_dir(slug) / "extracted" / "door_schedule.json"
    if source.exists() and raw is None:
        raise ValueError("extracted/door_schedule.json is missing or invalid JSON")
    if not raw:
        return {"inserted": 0, "updated": 0, "skipped": 0}

    payload = _normalize_schedule_payload(raw)
    await import_scope_metadata(project)

    existing_docs = [
        doc
        async for doc in db.line_items.find({"projectId": project_id}).sort(
            [("mark", 1), ("createdAt", 1)]
        )
    ]
    existing_keys = _distinct_keys(
        [
            {
                "mark": doc.get("mark"),
                "description": doc.get("description"),
                "raw_row": doc.get("description"),
            }
            for doc in existing_docs
        ],
        _identity,
    )
    existing = {key: doc for key, doc in zip(existing_keys, existing_docs)}

    openings = payload.get("openings", [])
    inserted = updated = skipped = 0
    bulk: list[InsertOne | UpdateOne] = []
    for key, item in zip(_distinct_keys(openings, _identity), openings):
        evidence = {
            "note": item.get("evidence_note"),
            "sheet": item.get("sheet") or payload.get("sheet"),
            "row": item.get("row"),
            "confidence": item.get("confidence"),
            "sourceFile": item.get("source_file") or payload.get("source_file"),
            "sourcePage": item.get("source_page"),
            "bbox": item.get("bbox"),
            "pageSize": item.get("page_size"),
        }
        fields = {
            "mark": door_number(item) or None,
            "description": item.get("description") or item.get("raw_row", ""),
            "size": item.get("size") or item.get("width"),
            "qty": item.get("qty", 1),
            "hwSet": item.get("hardware_set") or item.get("hw_set"),
            "division": item.get("division"),
            "handing": item.get("handing"),
            "finish": item.get("finish"),
            "fireRating": item.get("fire_rating"),
            "frameType": item.get("frame_type"),
            "wallType": item.get("wall_type"),
            # Derived from wallType before validation, and the bid-alternate tag
            # the opening carries. All three were extracted and then dropped here.
            "frameDepth": item.get("frame_depth"),
            "alternateGroup": item.get("alternate") or item.get("alternate_group"),
            "confidence": item.get("confidence"),
            "flags": item.get("flags", []),
            "evidence": evidence,
            "duplicateReason": item.get("duplicate_reason"),
            "updatedAt": _now(),
        }

        current = existing.get(key)
        if current is None:
            bulk.append(
                InsertOne(
                    {
                        "projectId": project_id,
                        "status": _status_for(item),
                        "addedByHand": False,
                        "createdAt": _now(),
                        **fields,
                    }
                )
            )
            inserted += 1
        elif current.get("confirmedAt") or current.get("addedByHand"):
            bulk.append(
                UpdateOne(
                    {"_id": current["_id"]},
                    {"$set": {"evidence": evidence, "updatedAt": _now()}},
                )
            )
            skipped += 1
        else:
            bulk.append(
                UpdateOne(
                    {"_id": current["_id"]},
                    {"$set": {"status": _status_for(item), **fields}},
                )
            )
            updated += 1

    if bulk:
        await db.line_items.bulk_write(bulk, ordered=False)

    return {"inserted": inserted, "updated": updated, "skipped": skipped}
async def import_scope_metadata(project: dict[str, Any]) -> bool:
    """PATCH project fields from extracted/scope_metadata.json when present."""
    slug, project_id = project["slug"], project["_id"]
    raw = _read_json(storage.project_dir(slug) / "extracted" / "scope_metadata.json")
    if not raw or not isinstance(raw, dict):
        return False

    field_map = {
        "project_name": "name",
        "name": "name",
        "brand": "brand",
        "address": "address",
        "city": "city",
        "state": "state",
        "location": "location",
        "architect": "architect",
        "gc": "gc",
        "initiator": "initiator",
        "bid_due_date": "bidDueDate",
    }
    updates: dict[str, Any] = {}
    for source_key, target_key in field_map.items():
        value = raw.get(source_key)
        if value is not None and value != "":
            updates[target_key] = value

    if not updates:
        return False

    updates["updatedAt"] = _now()
    await db.projects.update_one({"_id": project_id}, {"$set": updates})
    return True
async def import_addendum(project: dict[str, Any], job: dict[str, Any]) -> dict[str, int]:
    """Load review/addendum_diff.json onto the version Claude was reading."""
    slug = project["slug"]
    payload = _read_json(storage.project_dir(slug) / "review" / "addendum_diff.json")
    source = storage.project_dir(slug) / "review" / "addendum_diff.json"
    if source.exists() and payload is None:
        raise ValueError("review/addendum_diff.json is missing or invalid JSON")
    if not payload:
        return {"added": 0, "removed": 0, "changed": 0}

    version = (job.get("payload") or {}).get("version")
    if version is None:
        raise ValueError("ingest_addendum job missing payload.version")

    result = await db.versions.update_one(
        {"projectId": project["_id"], "version": int(version)},
        {
            "$set": {
                "addendumDiff": payload,
                "reconciled": False,
                "diffImportedAt": _now(),
            }
        },
    )
    if not result.matched_count:
        raise ValueError(f"version {version} not found for addendum diff import")

    return {
        "added": len(payload.get("added") or []),
        "removed": len(payload.get("removed") or []),
        "changed": len(payload.get("changed") or []),
    }
