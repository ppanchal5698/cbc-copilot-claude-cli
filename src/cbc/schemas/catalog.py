from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from cbc.schemas.common import ProductType


class ProductBase(BaseModel):
    part: str = Field(min_length=1)
    description: str = ""
    manufacturer: str | None = None
    division: str | None = None
    cost: float | None = None
    listPrice: float | None = None
    multiplier: float | None = None
    sellAt: float | None = None
    availability: str | None = None
    priceBookId: str | None = None
    priceBook: str | None = None
    xref: list[dict[str, str]] = []
    productType: ProductType | None = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    description: str | None = None
    manufacturer: str | None = None
    division: str | None = None
    cost: float | None = None
    listPrice: float | None = None
    multiplier: float | None = None
    sellAt: float | None = None
    availability: str | None = None
    priceBookId: str | None = None
    xref: list[dict[str, str]] | None = None
    productType: ProductType | None = None


class Product(ProductBase):
    id: str
    # What the price on this row means. `listPrice` is filled only for LIST rows,
    # so a caller that ignores this cannot read a net as though it were a list.
    priceBasis: str | None = None
    priceBasisNote: str | None = None
    netPrice: float | None = None
    updatedAt: datetime | None = None
    updatedBy: str | None = None


class PriceBookBase(BaseModel):
    vendor: str = Field(min_length=1)
    program: str | None = None
    multiplier: float | None = None
    categories: dict[str, float] | None = None
    effective: str | None = None
    protectedThrough: str | None = None
    lastReviewed: str | None = None
    steward: str | None = None
    kind: str | None = "price_book"
    note: str | None = None


class PriceBookCreate(PriceBookBase):
    pass


class PriceBookUpdate(BaseModel):
    program: str | None = None
    multiplier: float | None = None
    categories: dict[str, float] | None = None
    effective: str | None = None
    protectedThrough: str | None = None
    lastReviewed: str | None = None
    steward: str | None = None
    note: str | None = None


class PriceBook(PriceBookBase):
    id: str
    filename: str | None = None
    path: str | None = None
    partCount: int = 0
    updatedAt: datetime | None = None
