"""Audit trail (NFR-3).

Two actors touch this system - the estimator and Claude Code - and every change
either makes is recorded with who, what and when. Logging never blocks the
action it describes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from api.db import db


async def record(
    action: str,
    actor: str = "system",
    target: dict[str, Any] | None = None,
    before: Any = None,
    after: Any = None,
    note: str | None = None,
) -> None:
    try:
        await db.audit_log.insert_one(
            {
                "at": datetime.now(timezone.utc),
                "actor": actor,
                "action": action,
                "target": target or {},
                "before": before,
                "after": after,
                "note": note,
            }
        )
    except Exception:  # a failed log must never fail the request it describes
        pass
