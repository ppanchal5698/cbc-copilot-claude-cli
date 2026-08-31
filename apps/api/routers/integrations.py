"""Integration status visible to every signed-in user."""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


@router.get("")
async def integration_status() -> dict[str, Any]:
    p21_connected = bool(os.environ.get("P21_BASE_URL", "").strip())
    return {
        "p21": {
            "connected": p21_connected,
            "path": 1,
            "requirement": "NR-10",
            "status": "connected" if p21_connected else "deferred",
            "title": "P21 last-PO cost (Path 1)",
            "summary": (
                "Prophet 21 last purchase-order cost for regularly-bought items "
                "(Requirements Matrix 6.2)."
            ),
            "note": (
                "P21 is connected and read-only."
                if p21_connected
                else (
                    "P21 is not connected in this environment. Path 1 (last-PO cost) "
                    "is deferred while NR-10 feasibility is investigated. Pricing falls "
                    "back to list × multiplier (Path 2) or manual distributor / RFQ "
                    "entry (Path 3)."
                )
            ),
            "fallbacks": [
                "Path 2: vendor list price × multiplier tier",
                "Path 3: distributor lookup or vendor RFQ",
            ],
        },
    }
