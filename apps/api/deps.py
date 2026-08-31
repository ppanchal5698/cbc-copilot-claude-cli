"""Shared FastAPI dependencies."""
from __future__ import annotations

import secrets as pysecrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from cbc.config import settings

# Endpoints that must stay reachable without the internal service token.
PUBLIC_PATHS = frozenset({"/api/health", "/api/auth/verify"})


def get_actor(request: Request) -> str:
    """Return the authenticated actor set by InternalAuthMiddleware."""
    return getattr(request.state, "actor", "estimator")


Actor = Annotated[str, Depends(get_actor)]

# Who may reach provider credentials and the destructive routes. The role is read
# from the database, not from a header: the internal token authenticates the
# Next.js server, not the person behind it, so trusting a caller-supplied role
# would make every signed-in estimator an administrator.
ADMIN_ROLES = frozenset({"admin"})


async def require_admin(request: Request) -> str:
    from cbc.db import db

    actor = get_actor(request)
    user = await db.users.find_one({"email": actor.lower()}, {"role": 1})
    if not user or user.get("role") not in ADMIN_ROLES:
        raise HTTPException(
            403,
            f"{actor} is not permitted here. This needs one of: "
            + ", ".join(sorted(ADMIN_ROLES)),
        )
    return actor


AdminActor = Annotated[str, Depends(require_admin)]


class InternalAuthMiddleware(BaseHTTPMiddleware):
    """Require a shared service token on every /api route except the public set.

    The Next.js proxy and server-side fetches send X-Internal-Token plus
    X-Actor (from the signed-in session). Query-string actor= is ignored so a
    direct caller cannot spoof the audit trail.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if not path.startswith("/api/") or path in PUBLIC_PATHS:
            return await call_next(request)

        token = settings.internal_api_token
        if token:
            provided = request.headers.get("X-Internal-Token", "")
            if not pysecrets.compare_digest(provided, token):
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

        actor = request.headers.get("X-Actor", "").strip()
        if not actor:
            return JSONResponse(
                status_code=401,
                content={"detail": "X-Actor header required"},
            )
        request.state.actor = actor
        return await call_next(request)
