"""CBC Ops-Hub API.

Owns MongoDB and every business rule. The Next.js app is presentation; the
worker runs Claude Code. Quote arithmetic is delegated to the calc-engine MCP
server so the numbers on a customer proposal have exactly one implementation.

    uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import settings
from api.db import ensure_indexes
from api.routers import (
    auth,
    catalog,
    documents,
    jobs,
    line_items,
    price_books,
    projects,
    proposal,
    quote,
)

log = logging.getLogger("cbc.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    log.info("indexes ready; storage at %s", settings.storage_root)
    yield


app = FastAPI(
    title="CBC Ops-Hub API",
    version="0.1.0",
    description="Estimating and pricing desk for CBC - bid documents in, priced proposal out.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """A bad id or a bad enum is the caller's mistake, not a server fault."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


for router in (
    auth.router,
    projects.router,
    documents.router,
    line_items.router,
    quote.router,
    proposal.router,
    catalog.router,
    price_books.router,
    jobs.router,
):
    app.include_router(router)


@app.get("/api/health")
async def health() -> dict:
    from api.db import db

    try:
        await db.projects.database.command("ping")
        database = "up"
    except Exception as exc:  # surfaced, not swallowed - the UI shows this
        database = f"down: {exc}"

    return {
        "status": "ok" if database == "up" else "degraded",
        "database": database,
        "storageRoot": str(settings.storage_root),
        "sends": "disabled by design (NFR-1)",
    }
