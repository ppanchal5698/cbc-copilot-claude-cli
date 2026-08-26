"""MongoDB access for the CBC Ops-Hub API.

One motor client for the process. Collection accessors are plain attributes so
callers read as prose: `db.line_items.find({...})`.
"""
from __future__ import annotations

from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, TEXT

from api.config import settings

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


db = Collections()


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
    await db.products.create_index([("part", ASCENDING)], unique=True)
    await db.products.create_index([("division", ASCENDING)])
    await db.products.create_index(
        [("part", TEXT), ("description", TEXT), ("manufacturer", TEXT)],
        name="product_search",
    )
    await db.price_books.create_index([("vendor", ASCENDING), ("program", ASCENDING)])
    await db.jobs.create_index([("status", ASCENDING), ("createdAt", ASCENDING)])
    await db.jobs.create_index([("projectId", ASCENDING), ("createdAt", DESCENDING)])
    await db.audit_log.create_index([("at", DESCENDING)])
    await db.audit_log.create_index([("target.projectId", ASCENDING)])


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
