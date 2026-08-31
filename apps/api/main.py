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

from cbc.config import settings
from cbc.db import ensure_indexes, ensure_readonly_user
from cbc.pageindex import store as pageindex_store
from apps.api.deps import InternalAuthMiddleware
from apps.api.routers import (
    alternates,
    audit_log,
    auth,
    calls,
    catalog,
    document_index,
    documents,
    integrations,
    jobs,
    line_items,
    price_books,
    projects,
    proposal,
    quote,
    reference_data,
    settings as settings_router,
    terminal,
    users,
    versions,
)

log = logging.getLogger("cbc.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    await pageindex_store.ensure_indexes()
    # The catalog MCP server reads the page index with a credential that cannot
    # write. Provisioning it here means a pricing pass never needs the root URI,
    # which `provider.WITHHELD` keeps out of the Claude subprocess on purpose.
    if not await ensure_readonly_user():
        log.warning(
            "no read-only MongoDB user; the catalog server will refuse to read "
            "the page index rather than fall back to the writable connection"
        )
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
app.add_middleware(InternalAuthMiddleware)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """A bad id or a bad enum is the caller's mistake, not a server fault."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


for router in (
    auth.router,
    users.router,
    audit_log.router,
    projects.router,
    documents.router,
    line_items.router,
    quote.router,
    proposal.router,
    catalog.router,
    document_index.router,
    integrations.router,
    price_books.router,
    reference_data.router,
    jobs.router,
    calls.router,
    alternates.router,
    versions.router,
    settings_router.router,
    terminal.router,
):
    app.include_router(router)


@app.get("/api/health")
async def health() -> dict:
    from cbc.db import db
    from cbc.services import catalog_search

    try:
        await db.projects.database.command("ping")
        database = "up"
    except Exception as exc:  # surfaced, not swallowed - the UI shows this
        database = f"down: {exc}"

    return {
        "status": "ok" if database == "up" else "degraded",
        "database": database,
        "storageRoot": str(settings.storage_root),
        "catalogIndex": "ready" if catalog_search.index_available() else "missing",
        "documentIndexRoot": str(settings.document_index_root),
        "sends": "disabled by design (NFR-1)",
    }
