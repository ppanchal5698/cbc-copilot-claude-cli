"""Re-pricing a quote and rolling it up.

One implementation, called from three places that used to reach into the quote
router for it: the quote screen, the proposal screen, and the worker's sync after
a pricing pass.

The important property is that computing and storing are separate. `GET /quote`
called a function that wrote a row per line and upserted the totals, so two
browser tabs on one bid interleaved their writes, a `PATCH` landing between
another request's read and its write was silently reverted, and the page could
not be cached or safely retried. Reads now compute; only the routes that change
something persist.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from cbc.db import db
from cbc.services import pricing


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def lines_for(project_id) -> list[dict[str, Any]]:
    return await db.quote_lines.find({"projectId": project_id}).sort("division", 1).to_list(2000)


def tax_state(project: dict[str, Any], quote: dict[str, Any]) -> str | None:
    """Which jurisdiction decides the tax on this bid.

    "NONE" is the estimator saying there is no nexus. Unset means nobody has
    ruled, so the ship-to state decides. Collapsing both into null would let a
    deliberate "no tax" silently become "tax per the project state".
    """
    stored = quote.get("taxJurisdiction")
    return stored if stored else project.get("state")


def reprice(lines: list[dict[str, Any]], state: str | None, freight: float | None) -> dict:
    """Price every line in memory and roll them up. Writes nothing.

    Mutates the dicts it is given so the caller can render them, and reports which
    of them actually changed so a persisting caller writes only those.
    """
    changed: list[dict[str, Any]] = []
    for line in lines:
        priced = pricing.price_line(
            cost=line.get("cost"),
            margin=line.get("margin"),
            qty=line.get("qty", 1),
            division=line.get("division"),
        )
        stale = ("sell" not in line) or ("extended" not in line)
        differs = (line.get("sell"), line.get("extended"), line.get("margin")) != (
            priced["sell"],
            priced["extended"],
            priced["margin"],
        )
        line["sell"] = priced["sell"]
        line["extended"] = priced["extended"]
        line["margin"] = priced["margin"]
        # Why a line came back unpriced, so it reads as "needs a look" on the
        # screen rather than just being blank.
        line["priceError"] = priced.get("error")
        line["marginCheck"] = pricing.check_margin(line.get("division"), priced["margin"])
        if stale or differs or line.get("priceError") != priced.get("error"):
            changed.append(line)

    return {"totals": pricing.totals(lines, state, freight), "changed": changed}


async def totals_for(project: dict[str, Any]) -> tuple[dict, list[dict[str, Any]]]:
    """Current totals and priced lines, without touching the database."""
    quote = await db.quotes.find_one({"projectId": project["_id"]}) or {}
    lines = await lines_for(project["_id"])
    result = reprice(lines, tax_state(project, quote), quote.get("freight"))
    return result["totals"], lines


async def persist(project: dict[str, Any]) -> dict:
    """Re-price, store the results, and return the totals.

    Called from the routes that change something and from the worker once a
    pricing pass has landed - never from a read.
    """
    project_id = project["_id"]
    quote = await db.quotes.find_one({"projectId": project_id}) or {}
    state = tax_state(project, quote)

    lines = await lines_for(project_id)
    result = reprice(lines, state, quote.get("freight"))

    for line in result["changed"]:
        await db.quote_lines.update_one(
            {"_id": line["_id"]},
            {
                "$set": {
                    "sell": line["sell"],
                    "extended": line["extended"],
                    "margin": line["margin"],
                    "priceError": line["priceError"],
                    "marginCheck": line["marginCheck"],
                }
            },
        )

    totals = result["totals"]
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
