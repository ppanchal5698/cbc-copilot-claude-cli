"""Quote - editable cost, margin and quantity, with totals recomputed on the spot.

Every number here comes from `calc-engine` through `api/services/pricing.py`.
Nothing in this module does arithmetic on money.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from api.db import db, oid, serialise
from api.models import QuoteLineCreate, QuoteLineUpdate, QuoteSettings
from api.routers.projects import load
from api.services import audit, jobs, pricing, sync

router = APIRouter(prefix="/api/projects/{code}/quote", tags=["quote"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


STALE_DAYS = 180


async def _lines(project_id) -> list[dict[str, Any]]:
    return await db.quote_lines.find({"projectId": project_id}).sort("division", 1).to_list(2000)


def _lapsed(line: dict[str, Any]) -> bool:
    """True when the sheet this cost came from is past the review window.

    A lapsed price is not wrong, but it is unverified - the estimator decides.
    """
    effective = line.get("multiplierEffectiveDate")
    if not effective:
        return False
    try:
        return (date.today() - date.fromisoformat(str(effective))).days > STALE_DAYS
    except ValueError:
        return False


async def _recompute(project: dict[str, Any], actor: str = "system") -> dict[str, Any]:
    """Re-price every line and re-total. Called after any edit."""
    project_id = project["_id"]
    quote = await db.quotes.find_one({"projectId": project_id}) or {}
    # "NONE" is the estimator saying there is no nexus. Unset means nobody has
    # ruled, so the ship-to state decides. Collapsing both into null would let a
    # deliberate "no tax" silently become "tax per the project state".
    stored = quote.get("taxJurisdiction")
    state = stored if stored else project.get("state")

    lines = await _lines(project_id)
    for line in lines:
        priced = pricing.price_line(
            cost=line.get("cost"),
            margin=line.get("margin"),
            qty=line.get("qty", 1),
            division=line.get("division"),
        )
        stale = ("sell" not in line) or ("extended" not in line)
        if stale or (line.get("sell"), line.get("extended"), line.get("margin")) != (
            priced["sell"],
            priced["extended"],
            priced["margin"],
        ):
            await db.quote_lines.update_one(
                {"_id": line["_id"]},
                {
                    "$set": {
                        "sell": priced["sell"],
                        "extended": priced["extended"],
                        "margin": priced["margin"],
                        "marginCheck": pricing.check_margin(
                            line.get("division"), priced["margin"]
                        ),
                    }
                },
            )
            line.update(sell=priced["sell"], extended=priced["extended"], margin=priced["margin"])

    totals = pricing.totals(lines, state, quote.get("freight"))
    await db.quotes.update_one(
        {"projectId": project_id},
        {
            "$set": {
                **totals,
                "taxJurisdiction": state,
                "updatedAt": _now(),
                "quoteNumber": quote.get("quoteNumber") or f"Q-{project.get('code', '')}",
            },
            "$setOnInsert": {"projectId": project_id, "createdAt": _now()},
        },
        upsert=True,
    )
    return totals


@router.get("")
async def get_quote(code: str) -> dict[str, Any]:
    project = await load(code)
    totals = await _recompute(project)
    raw = await _lines(project["_id"])
    lines = [{**serialise(line), "lapsed": _lapsed(line)} for line in raw]

    groups: dict[str, dict[str, Any]] = {}
    for line in lines:
        key = line.get("division") or "Other"
        group = groups.setdefault(key, {"division": key, "lines": [], "subtotal": 0.0})
        group["lines"].append(line)
        group["subtotal"] = round(group["subtotal"] + (line.get("extended") or 0), 2)

    quote = await db.quotes.find_one({"projectId": project["_id"]})
    edited = [line for line in lines if line.get("marginOverridden") or line.get("addedByHand")]

    return {
        "quote": serialise(quote),
        "groups": sorted(groups.values(), key=lambda g: g["division"]),
        "totals": totals,
        "lineCount": len(lines),
        "edited": {
            "count": len(edited),
            "firstId": edited[0]["id"] if edited else None,
        },
        "lapsedCount": sum(1 for line in lines if line["lapsed"]),
    }


@router.patch("/settings")
async def update_settings(code: str, body: QuoteSettings, actor: str = "estimator") -> dict:
    project = await load(code)
    changes = body.model_dump(exclude_unset=True)
    await db.quotes.update_one(
        {"projectId": project["_id"]},
        {"$set": {**changes, "updatedAt": _now()}, "$setOnInsert": {"createdAt": _now()}},
        upsert=True,
    )
    await audit.record("quote.settings", actor, {"projectId": project["_id"]}, after=changes)
    return {"totals": await _recompute(project, actor)}


@router.post("/lines", status_code=201)
async def add_line(code: str, body: QuoteLineCreate, actor: str = "estimator") -> dict:
    project = await load(code)
    payload = body.model_dump(exclude_none=True)

    if body.productId:
        product = await db.products.find_one({"_id": oid(body.productId)})
        if product:
            payload.setdefault("part", product.get("part"))
            payload.setdefault("description", product.get("description", ""))
            payload.setdefault("division", product.get("division"))
            payload.setdefault("cost", product.get("cost"))
            payload["basis"] = f"Catalog · {product.get('priceBook') or 'manual'}"
            payload["costSource"] = "BOOK_PRICE"
            payload.pop("productId", None)

    document = {
        # Every priced field exists from the start, even when unpriced, so a
        # consumer never has to guess whether a missing key means zero or unknown.
        "sell": None,
        "extended": None,
        "margin": None,
        "cost": None,
        **payload,
        "projectId": project["_id"],
        "lineKey": f"hand-{_now().timestamp():.0f}",
        "addedByHand": True,
        "marginOverridden": False,
        "flags": [],
        "createdAt": _now(),
    }
    result = await db.quote_lines.insert_one(document)
    await audit.record(
        "quote.line_added",
        actor,
        {"projectId": project["_id"], "quoteLineId": result.inserted_id},
        after=payload.get("description"),
    )
    totals = await _recompute(project, actor)
    return {"line": serialise(await db.quote_lines.find_one({"_id": result.inserted_id})), "totals": totals}


@router.patch("/lines/{line_id}")
async def update_line(
    code: str, line_id: str, body: QuoteLineUpdate, actor: str = "estimator"
) -> dict:
    project = await load(code)
    line = await db.quote_lines.find_one({"_id": oid(line_id), "projectId": project["_id"]})
    if not line:
        raise HTTPException(404, "quote line not found")

    changes = body.model_dump(exclude_unset=True)
    reason = changes.pop("overrideReason", None)
    if not changes:
        return {"line": serialise(line), "totals": await _recompute(project, actor)}

    override = {
        "at": _now(),
        "by": actor,
        "before": {key: line.get(key) for key in changes},
        "after": changes,
        "reason": reason,
    }
    update: dict[str, Any] = {**changes, "updatedAt": _now()}
    if "margin" in changes:
        update["marginOverridden"] = True
        update["overrideReason"] = reason

    await db.quote_lines.update_one(
        {"_id": line["_id"]}, {"$set": update, "$push": {"overrides": override}}
    )
    await audit.record(
        "quote.line_edit",
        actor,
        {"projectId": project["_id"], "quoteLineId": line["_id"]},
        before=override["before"],
        after=changes,
        note=reason,
    )

    totals = await _recompute(project, actor)
    return {"line": serialise(await db.quote_lines.find_one({"_id": line["_id"]})), "totals": totals}


@router.delete("/lines/{line_id}")
async def delete_line(code: str, line_id: str, actor: str = "estimator") -> dict:
    project = await load(code)
    line = await db.quote_lines.find_one({"_id": oid(line_id), "projectId": project["_id"]})
    if not line:
        raise HTTPException(404, "quote line not found")

    await db.quote_lines.delete_one({"_id": line["_id"]})
    await audit.record(
        "quote.line_delete",
        actor,
        {"projectId": project["_id"], "quoteLineId": line["_id"]},
        before=line.get("description"),
    )
    return {"totals": await _recompute(project, actor)}


@router.post("/continue-to-proposal")
async def continue_to_proposal(code: str, actor: str = "estimator") -> dict:
    """Phase boundary: write the approved quote down, then enqueue the proposal build."""
    project = await load(code)
    await _recompute(project, actor)
    await sync.export_quote_lines(project)

    job = await jobs.enqueue("build_proposal", project["_id"], actor=actor)
    await db.projects.update_one(
        {"_id": project["_id"]},
        {"$set": {"stage": "proposal", "progress": 100, "updatedAt": _now()}},
    )
    await audit.record("project.continue_to_proposal", actor, {"projectId": project["_id"]})
    return {"job": serialise(job)}
