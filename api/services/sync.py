"""The bridge between Claude's JSON files and MongoDB.

Claude Code writes what it always wrote - `extracted/*.json`, `priced/*.json` -
so every agent, skill and test keeps working and the files stay the audit
artifact. This module moves that data into Mongo for the UI to serve, and pushes
estimator corrections back down before the next phase runs, so Claude's next pass
reads what the human actually confirmed.

Import is upsert-by-identity, never blind replace: a line the estimator has
already confirmed keeps its confirmation, and their edits are not clobbered by a
re-run.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bson import ObjectId

from api.db import db
from api.services import storage

# ── helpers ─────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _identity(item: dict[str, Any]) -> str:
    """Stable key for matching a re-extracted row to an existing line item."""
    mark = (item.get("mark") or item.get("door_number") or "").strip()
    if mark:
        return f"mark:{mark}"
    return "desc:" + (item.get("description") or item.get("raw_row") or "").strip().lower()[:80]


def _status_for(item: dict[str, Any]) -> str:
    if item.get("duplicate_of") or item.get("is_duplicate"):
        return "duplicate"
    confidence = item.get("confidence")
    if item.get("flags") or (confidence is not None and confidence < 0.75):
        return "needs_look"
    return "clear"


# ── extraction: files -> Mongo ──────────────────────────────────────────────


async def import_extraction(project: dict[str, Any]) -> dict[str, int]:
    """Load `extracted/door_schedule.json` into `lineItems`.

    Returns counts so the caller can report what a job actually changed.
    """
    slug, project_id = project["slug"], project["_id"]
    payload = _read_json(storage.project_dir(slug) / "extracted" / "door_schedule.json")
    if not payload:
        return {"inserted": 0, "updated": 0, "skipped": 0}

    existing = {
        _identity(doc): doc
        async for doc in db.line_items.find({"projectId": project_id})
    }

    inserted = updated = skipped = 0
    for item in payload.get("openings", []):
        key = _identity(item)
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
            "mark": item.get("mark") or item.get("door_number"),
            "description": item.get("description") or item.get("raw_row", ""),
            "size": item.get("size") or item.get("width"),
            "qty": item.get("qty", 1),
            "hwSet": item.get("hardware_set"),
            "division": item.get("division"),
            "handing": item.get("handing"),
            "finish": item.get("finish"),
            "fireRating": item.get("fire_rating"),
            "frameType": item.get("frame_type"),
            "wallType": item.get("wall_type"),
            "confidence": item.get("confidence"),
            "flags": item.get("flags", []),
            "evidence": evidence,
            "duplicateReason": item.get("duplicate_reason"),
            "updatedAt": _now(),
        }

        current = existing.get(key)
        if current is None:
            await db.line_items.insert_one(
                {
                    "projectId": project_id,
                    "status": _status_for(item),
                    "addedByHand": False,
                    "createdAt": _now(),
                    **fields,
                }
            )
            inserted += 1
        elif current.get("confirmedAt") or current.get("addedByHand"):
            # The estimator has ruled on this line. Refresh provenance only.
            await db.line_items.update_one(
                {"_id": current["_id"]},
                {"$set": {"evidence": evidence, "updatedAt": _now()}},
            )
            skipped += 1
        else:
            await db.line_items.update_one(
                {"_id": current["_id"]},
                {"$set": {"status": _status_for(item), **fields}},
            )
            updated += 1

    return {"inserted": inserted, "updated": updated, "skipped": skipped}


# ── extraction: Mongo -> files ──────────────────────────────────────────────


async def export_line_items(project: dict[str, Any]) -> Path:
    """Write the estimator-confirmed state down for Claude's next phase."""
    slug, project_id = project["slug"], project["_id"]
    openings = []
    async for doc in db.line_items.find({"projectId": project_id}).sort("mark", 1):
        if doc.get("status") == "duplicate" and doc.get("duplicateOf"):
            continue
        evidence = doc.get("evidence") or {}
        openings.append(
            {
                "mark": doc.get("mark"),
                "door_number": doc.get("mark"),
                "description": doc.get("description"),
                "size": doc.get("size"),
                "qty": doc.get("qty", 1),
                "hardware_set": doc.get("hwSet"),
                "division": doc.get("division"),
                "handing": doc.get("handing"),
                "finish": doc.get("finish"),
                "fire_rating": doc.get("fireRating"),
                "frame_type": doc.get("frameType"),
                "wall_type": doc.get("wallType"),
                "source_file": evidence.get("sourceFile"),
                "source_page": evidence.get("sourcePage"),
                "bbox": evidence.get("bbox"),
                "page_size": evidence.get("pageSize"),
                "confidence": doc.get("confidence"),
                "flags": doc.get("flags", []),
                "status": doc.get("status"),
                "confirmed_by": doc.get("confirmedBy"),
                "added_by_hand": doc.get("addedByHand", False),
            }
        )

    path = storage.project_dir(slug) / "extracted" / "door_schedule.json"
    _write_json(
        path,
        {
            "project": slug,
            "project_code": project.get("code"),
            "exported_at": _now().isoformat(),
            "source": "estimator-confirmed via Ops-Hub",
            "openings": openings,
        },
    )
    return path


# ── pricing: files -> Mongo ─────────────────────────────────────────────────


async def import_quote_lines(project: dict[str, Any]) -> dict[str, int]:
    """Load `priced/line_items.json` into `quoteLines`."""
    slug, project_id = project["slug"], project["_id"]
    payload = _read_json(storage.project_dir(slug) / "priced" / "line_items.json")
    if not payload:
        return {"inserted": 0, "updated": 0, "skipped": 0}

    existing = {
        doc.get("lineKey"): doc
        async for doc in db.quote_lines.find({"projectId": project_id})
    }

    inserted = updated = skipped = 0
    for index, line in enumerate(payload.get("lines", [])):
        key = line.get("line_id") or f"{line.get('part') or 'line'}-{index}"
        fields = {
            "lineKey": key,
            "part": line.get("part_number") or line.get("part"),
            "description": line.get("description", ""),
            "division": line.get("division") or line.get("group_type"),
            "group": line.get("group"),
            "qty": line.get("quantity", 1),
            "cost": line.get("cost"),
            "margin": line.get("margin"),
            "sell": line.get("sale_ea"),
            "extended": line.get("ext_price"),
            "basis": line.get("basis") or "Book price",
            "costSource": line.get("cost_source"),
            "costSourceDetail": line.get("cost_source_detail"),
            "multiplier": line.get("multiplier"),
            "multiplierTier": line.get("multiplier_tier"),
            "multiplierEffectiveDate": line.get("multiplier_effective_date"),
            "priceBookVersion": line.get("price_book_version"),
            "sourcePage": line.get("source_page"),
            "priceStatus": line.get("price_status"),
            "flags": line.get("flags", []),
            "updatedAt": _now(),
        }

        current = existing.get(key)
        if current is None:
            await db.quote_lines.insert_one(
                {
                    "projectId": project_id,
                    "addedByHand": False,
                    "marginOverridden": False,
                    "createdAt": _now(),
                    **fields,
                }
            )
            inserted += 1
        elif current.get("marginOverridden") or current.get("addedByHand"):
            # Keep the estimator's price; refresh only the provenance around it.
            await db.quote_lines.update_one(
                {"_id": current["_id"]},
                {
                    "$set": {
                        key_: fields[key_]
                        for key_ in (
                            "costSource",
                            "costSourceDetail",
                            "multiplier",
                            "multiplierTier",
                            "multiplierEffectiveDate",
                            "priceBookVersion",
                            "sourcePage",
                            "updatedAt",
                        )
                    }
                },
            )
            skipped += 1
        else:
            await db.quote_lines.update_one({"_id": current["_id"]}, {"$set": fields})
            updated += 1

    return {"inserted": inserted, "updated": updated, "skipped": skipped}


async def export_quote_lines(project: dict[str, Any]) -> Path:
    """Write the estimator-approved quote down for the proposal phase."""
    slug, project_id = project["slug"], project["_id"]
    lines = []
    async for doc in db.quote_lines.find({"projectId": project_id}):
        lines.append(
            {
                "line_id": doc.get("lineKey") or str(doc["_id"]),
                "group": doc.get("group") or doc.get("division") or "Other",
                "group_type": _group_type(doc.get("division")),
                "part_number": doc.get("part"),
                "description": doc.get("description"),
                "division": doc.get("division"),
                "quantity": doc.get("qty", 1),
                "cost": doc.get("cost"),
                "margin": doc.get("margin"),
                "sale_ea": doc.get("sell"),
                "ext_price": doc.get("extended"),
                "cost_source": doc.get("costSource"),
                "cost_source_detail": doc.get("costSourceDetail"),
                "multiplier": doc.get("multiplier"),
                "multiplier_tier": doc.get("multiplierTier"),
                "multiplier_effective_date": doc.get("multiplierEffectiveDate"),
                "price_book_version": doc.get("priceBookVersion"),
                "source_page": doc.get("sourcePage"),
                "price_status": doc.get("priceStatus"),
                "added_by_hand": doc.get("addedByHand", False),
                "flags": doc.get("flags", []),
            }
        )

    quote = await db.quotes.find_one({"projectId": project_id}) or {}
    path = storage.project_dir(slug) / "priced" / "line_items.json"
    _write_json(
        path,
        {
            "generated_by": "estimator-approved via Ops-Hub",
            "quote_number": quote.get("quoteNumber") or f"Q-{project.get('code', '')}",
            "quote_date": _now().date().isoformat(),
            "project": {
                "name": project.get("name"),
                "location": project.get("location"),
                "state": project.get("state"),
                "architect": project.get("architect"),
            },
            "customer": {"gc": project.get("gc"), "initiator": project.get("initiator")},
            "estimator": {"name": quote.get("estimatorName")},
            "lines": lines,
        },
    )
    return path


def _group_type(division: str | None) -> str:
    if not division:
        return "door"
    if division.startswith("10"):
        return "accessories"
    if division.startswith("06"):
        return "frp"
    return "door"
