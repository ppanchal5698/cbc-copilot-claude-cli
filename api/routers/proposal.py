"""Proposal - the customer-facing document, and the point where the system stops.

The API renders and serves it. It does not email it. NFR-1 is not negotiable:
the copilot drafts, sources and calculates - a human sends.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response

from api.config import settings
from api.db import db, serialise
from api.models import ProposalSettings
from api.routers.projects import load
from api.routers.quote import _lines, _recompute
from api.services import audit

sys.path.insert(0, str(settings.repo_root / "mcp-servers"))

router = APIRouter(prefix="/api/projects/{code}/proposal", tags=["proposal"])

VALIDITY_DAYS = 30
SECTION_TITLES = {
    "door": "Doors / Frames / Hardware",
    "accessories": "Restroom Accessories",
    "frp": "FRP Wall Panels",
    "other": "Other",
}

DEFAULT_EXCLUSIONS = [
    "Installation, unloading and hoisting are excluded; material F.O.B. jobsite.",
    "Hardware sets are excluded pending the architect resolving any duplicate listings.",
    "Hand dryer voltage per drawing note; electrical rough-in by others.",
    "FRP quantities are based on the finish plan; field measurement is the installer's responsibility.",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _section_of(division: str | None) -> str:
    if not division:
        return "door"
    if division.startswith("10"):
        return "accessories"
    if division.startswith("06"):
        return "frp"
    return "door"


async def _build(project: dict[str, Any], markup: float = 0.0) -> dict[str, Any]:
    totals = await _recompute(project)
    lines = await _lines(project["_id"])

    sections: dict[str, dict[str, Any]] = {}
    for line in lines:
        key = _section_of(line.get("division"))
        section = sections.setdefault(
            key, {"key": key, "title": SECTION_TITLES[key], "lines": [], "subtotal": 0.0}
        )
        unit = line.get("sell")
        extended = line.get("extended")
        if markup and unit is not None:
            unit = round(unit * (1 + markup), 2)
            extended = round(unit * float(line.get("qty") or 0), 2)
        section["lines"].append(
            {
                "part": line.get("part"),
                "qty": line.get("qty"),
                "uom": "EA",
                "description": (line.get("description") or "").upper(),
                "unitPrice": unit,
                "extPrice": extended,
                "priceStatus": line.get("priceStatus"),
            }
        )
        section["subtotal"] = round(section["subtotal"] + (extended or 0), 2)

    ordered = [sections[k] for k in ("door", "accessories", "frp", "other") if k in sections]
    grand = round(sum(s["subtotal"] for s in ordered) + (totals.get("tax") or 0), 2)

    return {
        "sections": ordered,
        "totals": {**totals, "markup": markup, "grandTotal": grand if markup else totals["grandTotal"]},
    }


@router.get("")
async def get_proposal(code: str) -> dict[str, Any]:
    project = await load(code)
    stored = await db.proposals.find_one({"projectId": project["_id"]}) or {}
    built = await _build(project, stored.get("markup", 0.0))

    flagged = await db.line_items.count_documents(
        {"projectId": project["_id"], "status": "needs_look"}
    )
    unpriced = await db.quote_lines.count_documents(
        {"projectId": project["_id"], "cost": None}
    )

    return {
        "proposal": {
            "proposalNo": stored.get("proposalNo") or f"Q-{project['code'].split('-')[-1]}",
            "date": (stored.get("date") or date.today()).isoformat()
            if not isinstance(stored.get("date"), str)
            else stored["date"],
            "validityDays": VALIDITY_DAYS,
            "customer": stored.get("customer") or {"name": project.get("gc")},
            "salesRep": stored.get("salesRep") or {"name": project.get("initiator")},
            "estimator": stored.get("estimator") or {},
            "markup": stored.get("markup", 0.0),
            "exclusions": stored.get("exclusions") or DEFAULT_EXCLUSIONS,
            "signoff": stored.get("signoff") or [],
            "sentAt": stored.get("sentAt"),
        },
        "project": serialise(project),
        **built,
        "readiness": {
            "flaggedLineItems": flagged,
            "unpricedQuoteLines": unpriced,
            "blocking": False,
            "note": "Flagged and unpriced lines are shown, not blocked - the estimator decides.",
        },
    }


@router.patch("")
async def update_proposal(code: str, body: ProposalSettings, actor: str = "estimator") -> dict:
    project = await load(code)
    changes = body.model_dump(exclude_unset=True)

    await db.proposals.update_one(
        {"projectId": project["_id"]},
        {
            "$set": {**changes, "updatedAt": _now()},
            "$setOnInsert": {
                "projectId": project["_id"],
                "proposalNo": f"Q-{project['code'].split('-')[-1]}",
                "date": date.today().isoformat(),
                "createdAt": _now(),
            },
        },
        upsert=True,
    )
    await audit.record("proposal.update", actor, {"projectId": project["_id"]}, after=changes)
    return await get_proposal(code)


@router.get("/render", response_class=HTMLResponse)
async def render_proposal(code: str) -> HTMLResponse:
    """Render the customer-facing HTML from the shared Jinja template."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    project = await load(code)
    data = await get_proposal(code)

    env = Environment(
        loader=FileSystemLoader(str(settings.templates_dir)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    blocks = [
        {
            "key": section["key"],
            "title": section["title"],
            "lines": section["lines"],
            "groups": [
                {
                    "name": section["title"],
                    "lines": [
                        {
                            "description": line["description"],
                            "part_number": line["part"],
                            "quantity": line["qty"],
                            "sale_ea": line["unitPrice"],
                            "ext_price": line["extPrice"],
                            "cost": None,
                            "margin": None,
                            "flags": [],
                        }
                        for line in section["lines"]
                    ],
                    "subtotal": section["subtotal"],
                }
            ],
        }
        for section in data["sections"]
    ]

    html = env.get_template("quotation.html").render(
        quote_number=data["proposal"]["proposalNo"],
        quote_date=data["proposal"]["date"],
        validity_days=VALIDITY_DAYS,
        project={
            "name": project.get("name"),
            "location": project.get("location"),
            "architect": project.get("architect"),
            "bid_due_date": None,
        },
        customer={"gc": project.get("gc"), "initiator": project.get("initiator")},
        estimator=data["proposal"]["estimator"],
        notes=data["proposal"]["exclusions"],
        blocks=blocks,
        totals={
            "subtotal": data["totals"]["subtotal"],
            "freight": data["totals"].get("freight"),
            "project_state": data["totals"].get("taxJurisdiction"),
            "tax_rate": data["totals"]["taxRate"],
            "tax": data["totals"]["tax"],
            "grand_total": data["totals"]["grandTotal"],
        },
        flag_count=data["readiness"]["flaggedLineItems"],
    )
    return HTMLResponse(html)


@router.get("/pdf")
async def proposal_pdf(code: str) -> Response:
    """Download the proposal as a PDF.

    Rendered locally - no converter is fetched from the internet. If no renderer
    is installed the caller is told plainly rather than handed a broken file.
    """
    html = (await render_proposal(code)).body.decode("utf-8")

    try:
        from weasyprint import HTML  # type: ignore
    except ImportError:
        raise HTTPException(
            501,
            "No local PDF renderer installed. Run `python -m pip install weasyprint` "
            "or use the browser's Print to PDF on the proposal view.",
        )

    pdf_bytes = HTML(string=html, base_url=str(settings.repo_root)).write_pdf()
    project = await load(code)
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{project["code"]}-proposal.pdf"'},
    )


@router.post("/complete")
async def mark_complete(code: str, actor: str = "estimator") -> dict:
    """Record the estimator's sign-off. Deliberately does not send anything (NFR-1)."""
    project = await load(code)
    await db.proposals.update_one(
        {"projectId": project["_id"]},
        {
            "$set": {"completedAt": _now(), "completedBy": actor},
            "$push": {
                "signoff": {"role": "estimator", "by": actor, "at": _now(), "state": "complete"}
            },
        },
        upsert=True,
    )
    await audit.record("proposal.mark_complete", actor, {"projectId": project["_id"]})
    return {
        "status": "complete",
        "sent": False,
        "message": "Draft ready for estimator review. Nothing has been sent.",
    }
