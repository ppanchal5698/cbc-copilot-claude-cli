"""Product catalog - the parts CBC can quote.

Claude maintains the bulk of this through price-book ingestion; the estimator can
search, add, edit and remove by hand. The search endpoint also backs the "add
anything the drawings do not carry" composer on the extraction screen.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pymongo.errors import DuplicateKeyError

from api.db import db, oid, serialise
from api.models import ProductCreate, ProductUpdate
from api.services import audit, pricing

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _derive_sell(product: dict[str, Any]) -> float | None:
    """Sell follows the division's margin divisor unless a price is set explicitly."""
    if product.get("sellAt") is not None:
        return product["sellAt"]
    if product.get("cost") is None:
        return None
    priced = pricing.price_line(
        cost=product["cost"], margin=None, qty=1, division=product.get("division")
    )
    return priced["sell"]


@router.get("/products")
async def search_products(
    q: str | None = None,
    division: str | None = None,
    manufacturer: str | None = None,
    limit: int = Query(default=50, le=200),
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if division:
        query["division"] = division
    if manufacturer:
        query["manufacturer"] = manufacturer
    if q:
        # Prefix match on part number first - an estimator typing "150CX" wants
        # that part, not every description containing the word.
        query["$or"] = [
            {"part": {"$regex": f"^{q}", "$options": "i"}},
            {"part": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"manufacturer": {"$regex": q, "$options": "i"}},
        ]

    products = await db.products.find(query).sort("part", 1).to_list(limit)
    divisions = await db.products.aggregate(
        [{"$group": {"_id": "$division", "n": {"$sum": 1}}}, {"$sort": {"_id": 1}}]
    ).to_list(50)

    return {
        "products": [{**serialise(p), "sellAt": _derive_sell(p)} for p in products],
        "total": await db.products.count_documents(query),
        "divisions": [
            {"division": row["_id"], "count": row["n"]} for row in divisions if row["_id"]
        ],
    }


@router.get("/products/{product_id}")
async def get_product(product_id: str) -> dict[str, Any]:
    product = await db.products.find_one({"_id": oid(product_id)})
    if not product:
        raise HTTPException(404, "product not found")

    book = None
    if product.get("priceBookId"):
        book = await db.price_books.find_one({"_id": product["priceBookId"]})

    return {
        "product": {**serialise(product), "sellAt": _derive_sell(product)},
        "priceBook": serialise(book) if book else None,
        "marginBand": pricing.band_for_division(product.get("division")),
    }


def _coerce_book_id(changes: dict[str, Any]) -> dict[str, Any]:
    """Store priceBookId as an ObjectId - the price-book routes query it as one."""
    if changes.get("priceBookId"):
        changes["priceBookId"] = oid(changes["priceBookId"])
    return changes


@router.post("/products", status_code=201)
async def create_product(body: ProductCreate, actor: str = "estimator") -> dict:
    document = _coerce_book_id(
        {**body.model_dump(exclude_none=True), "updatedAt": _now(), "updatedBy": actor}
    )
    try:
        result = await db.products.insert_one(document)
    except DuplicateKeyError:
        raise HTTPException(409, f"part {body.part} already exists in the catalog")

    document["_id"] = result.inserted_id
    await audit.record("catalog.create", actor, {"productId": result.inserted_id}, after=body.part)
    return {**serialise(document), "sellAt": _derive_sell(document)}


@router.patch("/products/{product_id}")
async def update_product(product_id: str, body: ProductUpdate, actor: str = "estimator") -> dict:
    product = await db.products.find_one({"_id": oid(product_id)})
    if not product:
        raise HTTPException(404, "product not found")

    changes = _coerce_book_id(body.model_dump(exclude_unset=True))
    if not changes:
        return {**serialise(product), "sellAt": _derive_sell(product)}

    await db.products.update_one(
        {"_id": product["_id"]}, {"$set": {**changes, "updatedAt": _now(), "updatedBy": actor}}
    )
    await audit.record(
        "catalog.update",
        actor,
        {"productId": product["_id"]},
        before={k: product.get(k) for k in changes},
        after=changes,
    )
    updated = await db.products.find_one({"_id": product["_id"]})
    return {**serialise(updated), "sellAt": _derive_sell(updated)}


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(product_id: str, actor: str = "estimator") -> None:
    product = await db.products.find_one({"_id": oid(product_id)})
    if not product:
        raise HTTPException(404, "product not found")

    await db.products.delete_one({"_id": product["_id"]})
    await audit.record(
        "catalog.delete", actor, {"productId": product["_id"]}, before=product.get("part")
    )
