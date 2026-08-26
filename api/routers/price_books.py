"""Price books and multiplier programs.

Uploading a book enqueues an ingest job, so the next bid Claude prices is using
the sheet purchasing just loaded. Staleness is surfaced rather than suppressed -
NFR-10 has no named owner yet, and pretending otherwise would hide the risk.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from api.config import settings
from api.db import db, oid, serialise
from api.models import PriceBookCreate, PriceBookUpdate
from api.services import audit, jobs, storage

router = APIRouter(prefix="/api/price-books", tags=["price-books"])

STALE_DAYS = 180


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _age_days(effective: str | None) -> int | None:
    if not effective:
        return None
    try:
        return (date.today() - date.fromisoformat(effective)).days
    except ValueError:
        return None


def _decorate(book: dict[str, Any]) -> dict[str, Any]:
    age = _age_days(book.get("effective"))
    return {
        **serialise(book),
        "ageDays": age,
        "stale": age is not None and age > STALE_DAYS,
        "undated": book.get("effective") is None,
    }


@router.get("")
async def list_price_books() -> dict[str, Any]:
    books = await db.price_books.find().sort([("vendor", 1), ("program", 1)]).to_list(200)
    decorated = [_decorate(b) for b in books]
    return {
        "priceBooks": decorated,
        "counts": {
            "total": len(decorated),
            "stale": sum(1 for b in decorated if b["stale"]),
            "undated": sum(1 for b in decorated if b["undated"]),
        },
        "stewardship": {
            "owner": None,
            "cadence": None,
            "note": "NFR-10 is open - no owner or refresh cadence has been assigned.",
        },
    }


@router.get("/{book_id}")
async def get_price_book(book_id: str) -> dict[str, Any]:
    book = await db.price_books.find_one({"_id": oid(book_id)})
    if not book:
        raise HTTPException(404, "price book not found")

    parts = await db.products.find({"priceBookId": book["_id"]}).sort("part", 1).to_list(500)
    return {"priceBook": _decorate(book), "parts": serialise(parts), "partCount": len(parts)}


@router.post("", status_code=201)
async def create_price_book(body: PriceBookCreate, actor: str = "purchasing") -> dict:
    document = {**body.model_dump(exclude_none=True), "partCount": 0, "updatedAt": _now()}
    result = await db.price_books.insert_one(document)
    document["_id"] = result.inserted_id
    await audit.record(
        "price_book.create", actor, {"priceBookId": result.inserted_id}, after=body.vendor
    )
    return _decorate(document)


@router.post("/{book_id}/file", status_code=201)
async def upload_price_book_file(
    book_id: str,
    file: UploadFile = File(...),
    actor: str = Form("purchasing"),
) -> dict:
    """Attach the sheet and ask Claude to read it into the catalog."""
    book = await db.price_books.find_one({"_id": oid(book_id)})
    if not book:
        raise HTTPException(404, "price book not found")

    payload = await file.read()
    if len(payload) > settings.max_upload_bytes:
        raise HTTPException(413, f"file exceeds {settings.max_upload_mb} MB")

    settings.pricebook_dir.mkdir(parents=True, exist_ok=True)
    target = storage.unique_filename(settings.pricebook_dir, file.filename or "pricebook.pdf")
    target.write_bytes(payload)

    await db.price_books.update_one(
        {"_id": book["_id"]},
        {
            "$set": {
                "filename": target.name,
                "path": storage.relative(target),
                "bytes": len(payload),
                "uploadedAt": _now(),
                "updatedAt": _now(),
            }
        },
    )

    job = await jobs.enqueue(
        "ingest_pricebook",
        payload={"priceBookId": str(book["_id"]), "filename": target.name},
        actor=actor,
    )
    await audit.record("price_book.upload", actor, {"priceBookId": book["_id"]}, after=target.name)
    return {"priceBook": _decorate(await db.price_books.find_one({"_id": book["_id"]})), "job": serialise(job)}


@router.get("/{book_id}/file")
async def download_price_book(book_id: str) -> FileResponse:
    book = await db.price_books.find_one({"_id": oid(book_id)})
    if not book or not book.get("path"):
        raise HTTPException(404, "no file attached to this price book")

    path = storage.absolute(book["path"])
    if not path.exists():
        raise HTTPException(410, f"file missing on disk: {book['path']}")
    return FileResponse(path, filename=book.get("filename") or path.name)


@router.patch("/{book_id}")
async def update_price_book(book_id: str, body: PriceBookUpdate, actor: str = "purchasing") -> dict:
    book = await db.price_books.find_one({"_id": oid(book_id)})
    if not book:
        raise HTTPException(404, "price book not found")

    changes = body.model_dump(exclude_unset=True)
    if not changes:
        return _decorate(book)

    await db.price_books.update_one({"_id": book["_id"]}, {"$set": {**changes, "updatedAt": _now()}})

    # A changed multiplier repricies every part on this program.
    if "multiplier" in changes and changes["multiplier"]:
        await db.products.update_many(
            {"priceBookId": book["_id"], "listPrice": {"$ne": None}},
            [
                {
                    "$set": {
                        "multiplier": changes["multiplier"],
                        "cost": {
                            "$round": [{"$multiply": ["$listPrice", changes["multiplier"]]}, 2]
                        },
                        "updatedAt": _now(),
                        "updatedBy": actor,
                    }
                }
            ],
        )

    await audit.record(
        "price_book.update",
        actor,
        {"priceBookId": book["_id"]},
        before={k: book.get(k) for k in changes},
        after=changes,
    )
    return _decorate(await db.price_books.find_one({"_id": book["_id"]}))


@router.post("/{book_id}/mark-reviewed")
async def mark_reviewed(book_id: str, actor: str = "purchasing") -> dict:
    book = await db.price_books.find_one({"_id": oid(book_id)})
    if not book:
        raise HTTPException(404, "price book not found")

    today = date.today().isoformat()
    await db.price_books.update_one(
        {"_id": book["_id"]}, {"$set": {"lastReviewed": today, "updatedAt": _now()}}
    )
    await audit.record("price_book.reviewed", actor, {"priceBookId": book["_id"]}, after=today)
    return _decorate(await db.price_books.find_one({"_id": book["_id"]}))


@router.delete("/{book_id}", status_code=204)
async def delete_price_book(book_id: str, actor: str = "purchasing") -> None:
    """Remove the program. Products priced under it are kept but marked orphaned.

    Deleting a book must not silently vaporise catalog rows a live quote points at.
    """
    book = await db.price_books.find_one({"_id": oid(book_id)})
    if not book:
        raise HTTPException(404, "price book not found")

    await db.products.update_many(
        {"priceBookId": book["_id"]},
        {"$set": {"priceBookId": None, "orphanedFrom": book.get("vendor"), "updatedAt": _now()}},
    )
    await db.price_books.delete_one({"_id": book["_id"]})
    await audit.record(
        "price_book.delete",
        actor,
        {"priceBookId": book["_id"]},
        before=book.get("vendor"),
        note="products retained, marked orphaned",
    )
