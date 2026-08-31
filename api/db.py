"""MongoDB access for the CBC Ops-Hub API.

One motor client for the process. Collection accessors are plain attributes so
callers read as prose: `db.line_items.find({...})`.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from urllib.parse import quote_plus, urlsplit

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, TEXT
from pymongo.errors import DuplicateKeyError, OperationFailure, PyMongoError

from api.config import settings
from api.schemas.common import EXCLUSIVE_JOB_TYPES

log = logging.getLogger("cbc.api.db")

_client: AsyncIOMotorClient | None = None


def client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongodb_uri, tz_aware=True)
    return _client


def database() -> AsyncIOMotorDatabase:
    return client()[settings.mongodb_db]


class Collections:
    """Named handles, resolved lazily so tests can point at another database."""

    @property
    def users(self):
        return database()["users"]

    @property
    def projects(self):
        return database()["projects"]

    @property
    def documents(self):
        return database()["documents"]

    @property
    def line_items(self):
        return database()["lineItems"]

    @property
    def quote_lines(self):
        return database()["quoteLines"]

    @property
    def quotes(self):
        return database()["quotes"]

    @property
    def proposals(self):
        return database()["proposals"]

    @property
    def products(self):
        return database()["products"]

    @property
    def price_books(self):
        return database()["priceBooks"]

    @property
    def jobs(self):
        return database()["jobs"]

    @property
    def audit_log(self):
        return database()["auditLog"]

    @property
    def calls(self):
        return database()["calls"]

    @property
    def versions(self):
        return database()["estimateVersions"]

    @property
    def counters(self):
        """Monotonic sequences. `_id` is the counter name, `seq` is the value."""
        return database()["counters"]

    @property
    def settings(self):
        """Installation settings - one document per concern, `_id` is the name."""
        return database()["settings"]

    @property
    def document_indexes(self):
        """Deep-index metadata: progress, status, version pointers."""
        return database()["documentIndexes"]


db = Collections()


async def _replace_index(collection, name: str, keys, **options) -> None:
    """Create an index, replacing an existing one whose options differ.

    `create_index` is idempotent only while the options match; changing them on an
    index that already exists raises rather than migrating, which would leave a
    tightened constraint silently un-applied on every database that already had
    the old one - that is, all of them.
    """
    try:
        await collection.create_index(keys, name=name, **options)
        return
    except OperationFailure as exc:
        if exc.code not in (85, 86):  # IndexOptionsConflict, IndexKeySpecsConflict
            raise
    await collection.drop_index(name)
    await collection.create_index(keys, name=name, **options)


async def ensure_indexes() -> None:
    """Idempotent index setup, run at startup."""
    await db.users.create_index([("email", ASCENDING)], unique=True)
    await db.projects.create_index([("code", ASCENDING)], unique=True)
    await db.projects.create_index([("slug", ASCENDING)], unique=True)
    await db.projects.create_index([("stage", ASCENDING), ("bidDue", ASCENDING)])
    await db.documents.create_index([("projectId", ASCENDING)])
    await db.line_items.create_index([("projectId", ASCENDING), ("status", ASCENDING)])
    await db.line_items.create_index([("projectId", ASCENDING), ("mark", ASCENDING)])
    await db.quote_lines.create_index([("projectId", ASCENDING), ("division", ASCENDING)])
    await db.quotes.create_index([("projectId", ASCENDING)], unique=True)
    await db.proposals.create_index([("projectId", ASCENDING)])
    # Hager's 1234 and Rockwood's 1234 are different parts. A unique index on
    # `part` alone made the price-book ingest upsert one over the other, so the
    # second vendor's sheet silently replaced the first vendor's costs.
    for legacy in ("part_1",):  # the old part-only unique index
        try:
            await db.products.drop_index(legacy)
            log.info("dropped legacy index products.%s", legacy)
        except OperationFailure:
            pass
    await db.products.create_index([("part", ASCENDING)])
    await db.products.create_index([("division", ASCENDING)])
    try:
        await _replace_index(
            db.products,
            "product_identity",
            [("manufacturer", ASCENDING), ("part", ASCENDING)],
            unique=True,
        )
    except DuplicateKeyError:
        log.error(
            "products already holds two rows with the same manufacturer and part, so "
            "the unique index could not be built. Run scripts/dedupe_products.py, "
            "then restart. Ingest is keyed on (manufacturer, part) either way."
        )
    await db.products.create_index(
        [("part", TEXT), ("description", TEXT), ("manufacturer", TEXT)],
        name="product_search",
    )
    await db.price_books.create_index([("vendor", ASCENDING), ("program", ASCENDING)])
    await db.jobs.create_index([("status", ASCENDING), ("createdAt", ASCENDING)])
    await db.jobs.create_index([("projectId", ASCENDING), ("createdAt", DESCENDING)])
    await _replace_index(
        db.jobs,
        "exclusive_active_job",
        [("projectId", ASCENDING), ("type", ASCENDING)],
        unique=True,
        partialFilterExpression={
            "status": {"$in": ["queued", "running"]},
            # Without this the index also covered `ingest_pricebook`, which carries
            # no project - so two pending uploads shared the key (null, type) and
            # the second was silently dropped in favour of the first.
            "type": {"$in": list(EXCLUSIVE_JOB_TYPES)},
        },
    )
    await db.jobs.create_index([("status", ASCENDING), ("heartbeatAt", ASCENDING)])
    await db.audit_log.create_index([("at", DESCENDING)])
    await db.audit_log.create_index([("target.projectId", ASCENDING)])
    await db.calls.create_index([("projectId", ASCENDING), ("createdAt", DESCENDING)])
    await _replace_index(
        db.versions,
        "project_version",
        [("projectId", ASCENDING), ("version", DESCENDING)],
        unique=True,
    )
    # Alternates are queried per group on both the extraction and quote screens.
    await db.line_items.create_index([("projectId", ASCENDING), ("alternateGroup", ASCENDING)])
    await db.quote_lines.create_index([("projectId", ASCENDING), ("alternateGroup", ASCENDING)])
    await db.document_indexes.create_index([("documentId", ASCENDING)], unique=True)
    await db.document_indexes.create_index(
        [("clientId", ASCENDING), ("documentType", ASCENDING), ("effectiveDate", DESCENDING)]
    )
    await db.document_indexes.create_index([("status", ASCENDING), ("updatedAt", DESCENDING)])


def oid(value: str | ObjectId) -> ObjectId:
    """Coerce to ObjectId, raising a ValueError the routers turn into a 400."""
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(value)
    except (InvalidId, TypeError) as exc:
        raise ValueError(f"not a valid id: {value!r}") from exc


def serialise(document: Any) -> Any:
    """Recursively turn ObjectId into str so a document is JSON-safe."""
    if isinstance(document, list):
        return [serialise(item) for item in document]
    if isinstance(document, dict):
        return {
            ("id" if key == "_id" else key): serialise(value) for key, value in document.items()
        }
    if isinstance(document, ObjectId):
        return str(document)
    return document


# ── read-only access for the catalog MCP server ─────────────────────────────
#
# `MONGODB_URI` authenticates as root@admin. That is right for the API, which
# owns every collection, and wrong for the one thing Claude Code is allowed to
# reach: the catalog server reads products and price books and asserts at import
# that it exposes no write tools.
#
# That assertion only governs the tools. It says nothing about the credentials
# the server holds, and until this existed the server held the superuser's - so
# "the catalog is read-only" was a convention rather than something the database
# would enforce.

READONLY_USER = "cbc_catalog_ro"


def _readonly_password() -> str:
    return os.environ.get("MONGODB_READONLY_PASSWORD", "cbc_catalog_ro_local_dev")


def readonly_uri() -> str | None:
    """A connection string that cannot write, or None when there isn't one.

    `MONGODB_READONLY_URI` wins: in production the user is provisioned by whoever
    owns the cluster and handed over as a secret, not created by an application
    at startup.
    """
    explicit = os.environ.get("MONGODB_READONLY_URI")
    if explicit:
        return explicit

    parsed = urlsplit(settings.mongodb_uri)
    if not parsed.hostname:
        return None

    host = parsed.hostname + (f":{parsed.port}" if parsed.port else "")
    credentials = f"{quote_plus(READONLY_USER)}:{quote_plus(_readonly_password())}"
    query = parsed.query or f"authSource={settings.mongodb_db}"
    return f"{parsed.scheme}://{credentials}@{host}{parsed.path or ''}?{query}"


async def ensure_readonly_user() -> bool:
    """Create or refresh the read-only user. True when one is usable.

    Idempotent, and a no-op when the cluster already provides the credentials.
    Failure is reported rather than raised: a pricing pass falling back to the
    writable URI is worse than ideal, but a pipeline that will not start at all
    because of a privilege refinement is worse still. The caller says which
    happened.
    """
    if os.environ.get("MONGODB_READONLY_URI"):
        return True

    database_name = settings.mongodb_db
    roles = [{"role": "read", "db": database_name}]
    try:
        target = client()[database_name]
        try:
            await target.command(
                "createUser", READONLY_USER, pwd=_readonly_password(), roles=roles
            )
        except OperationFailure as exc:
            if exc.code != 51003:  # already exists
                raise
            # Keep it aligned with the configured password and role on every boot.
            await target.command(
                "updateUser", READONLY_USER, pwd=_readonly_password(), roles=roles
            )
        return True
    except (OperationFailure, PyMongoError):
        return False
