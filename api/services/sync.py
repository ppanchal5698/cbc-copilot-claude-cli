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

import hashlib
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


def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _normalize_schedule_payload(payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
    """Accept legacy shapes and field aliases before import."""
    if isinstance(payload, list):
        payload = {"openings": payload}
    if not isinstance(payload, dict):
        raise ValueError("extracted/door_schedule.json must be a JSON object or openings array")

    openings = []
    for item in payload.get("openings", []):
        if not isinstance(item, dict):
            continue
        if item.get("hardware_set") is None and item.get("hw_set") is not None:
            item = {**item, "hardware_set": item["hw_set"]}
        if item.get("door_number") is None and item.get("mark"):
            item = {**item, "door_number": item["mark"]}
        openings.append(item)
    return {**payload, "openings": openings}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def door_number(item: dict[str, Any]) -> str:
    """The grouping key, whichever of the two names it arrived under.

    `door_number` is what the parser, the agents and the validator emit; `mark` is
    what the Mongo document calls it. Two names for the key the whole quote groups
    by is a standing trap - it is read here, once, so nothing downstream has to
    guess which one is populated.
    """
    return str(item.get("door_number") or item.get("mark") or "").strip()


def _identity(item: dict[str, Any]) -> str:
    """Stable key for matching a re-extracted row to an existing line item."""
    mark = door_number(item)
    if mark:
        return f"mark:{mark}"
    return "desc:" + (item.get("description") or item.get("raw_row") or "").strip().lower()[:80]


def _distinct_keys(items: list[dict[str, Any]], identity) -> list[str]:
    """Per-row keys, unique within one payload.

    A schedule really can list the same mark twice, and the plain identity made
    every repeat collide: the lookup built before the loop held one of them, so
    both rows saw "no match" and both inserted - fresh duplicates on every run,
    with the older copy orphaned and never updated again. Numbering the repeats
    keeps each row matched to its own record, and keeps that stable across runs
    because the schedule order is stable.
    """
    seen: dict[str, int] = {}
    keys = []
    for item in items:
        base = identity(item)
        seen[base] = seen.get(base, 0) + 1
        keys.append(base if seen[base] == 1 else f"{base}#{seen[base]}")
    return keys


def _status_for(item: dict[str, Any]) -> str:
    if item.get("duplicate_of") or item.get("is_duplicate"):
        return "duplicate"
    confidence = item.get("confidence")
    if item.get("flags") or (confidence is not None and confidence < 0.75):
        return "needs_look"
    return "clear"


def _sane_cost(line: dict[str, Any]) -> tuple[float | None, list[str]]:
    """A cost Claude wrote, or None with a flag saying why it was not taken.

    The API schema bounds what an estimator can type, but a pipeline run writes
    straight into Mongo. A negative or non-numeric cost is not priceable, and
    NFR-2 says an unusable value is flagged rather than guessed at - so it lands
    as unpriced with a reason instead of as a number nothing can divide by.
    """
    raw = line.get("cost")
    flags = list(line.get("flags") or [])
    if raw is None:
        return None, flags
    try:
        cost = float(raw)
    except (TypeError, ValueError):
        return None, flags + [f"unreadable cost {raw!r} - priced manually"]
    if cost < 0:
        return None, flags + [f"negative cost {cost} - priced manually"]
    return cost, flags


def _content_key(line: dict[str, Any]) -> str:
    if line.get("line_id"):
        return str(line["line_id"])
    material = "|".join(
        str(line.get(field) or "")
        for field in ("part_number", "part", "description", "division")
    ).strip().lower()
    return "auto:" + hashlib.sha1(material.encode("utf-8")).hexdigest()[:16]


# ── extraction: files -> Mongo ──────────────────────────────────────────────


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

    existing = {
        _identity(doc): doc
        async for doc in db.line_items.find({"projectId": project_id})
    }

    openings = payload.get("openings", [])
    inserted = updated = skipped = 0
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
    source = storage.project_dir(slug) / "priced" / "line_items.json"
    if source.exists() and payload is None:
        raise ValueError("priced/line_items.json is missing or invalid JSON")
    if not payload:
        return {"inserted": 0, "updated": 0, "skipped": 0}

    existing = {
        doc.get("lineKey"): doc
        async for doc in db.quote_lines.find({"projectId": project_id})
    }

    # `line_id` when Claude supplied one, otherwise derived from the line's own
    # content. The previous fallback keyed on list position, so re-ordering a
    # re-priced quote gave every line a new key and duplicated the lot.
    priced_lines = payload.get("lines", [])
    inserted = updated = skipped = 0
    for key, line in zip(_distinct_keys(priced_lines, _content_key), priced_lines):
        cost, flags = _sane_cost(line)
        fields = {
            "lineKey": key,
            "part": line.get("part_number") or line.get("part"),
            "description": line.get("description", ""),
            "division": line.get("division") or line.get("group_type"),
            "group": line.get("group"),
            "qty": line.get("quantity", 1),
            "cost": cost,
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
            "flags": flags,
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


# ── addendum / proposal: files -> Mongo ─────────────────────────────────────


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


async def import_proposal_artifacts(project: dict[str, Any]) -> dict[str, bool]:
    """Record Claude's proposal artifacts without replacing API-rendered totals."""
    slug = project["slug"]
    root = storage.project_dir(slug)
    artifacts = {
        "quotationHtml": (root / "quotation.html").exists(),
        "reviewFlags": (root / "review" / "review_flags.json").exists(),
        "reviewSummary": (root / "review" / "review_summary.html").exists(),
        "emailDraft": (root / "review" / "quotation_email_draft.md").exists(),
    }
    paths: dict[str, str] = {}
    for field, rel in {
        "quotationHtmlPath": "quotation.html",
        "reviewFlagsPath": "review/review_flags.json",
        "reviewSummaryPath": "review/review_summary.html",
        "emailDraftPath": "review/quotation_email_draft.md",
    }.items():
        target = root / rel
        if target.exists():
            paths[field] = storage.relative(target)

    await db.proposals.update_one(
        {"projectId": project["_id"]},
        {
            "$set": {
                **paths,
                "claudeArtifacts": artifacts,
                "artifactsImportedAt": _now(),
                "updatedAt": _now(),
            },
            "$setOnInsert": {
                "projectId": project["_id"],
                "createdAt": _now(),
            },
        },
        upsert=True,
    )
    return artifacts
