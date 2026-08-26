"""Pydantic schemas for the CBC Ops-Hub API.

These mirror the MongoDB collections. Field names stay camelCase to match what
the Next.js client consumes without a translation layer.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field

# ── shared vocabularies ─────────────────────────────────────────────────────

LineStatus = Literal["clear", "needs_look", "duplicate", "by_hand"]
Stage = Literal["intake", "extraction", "quote", "proposal"]
JobType = Literal[
    "extract_bid_set",
    "rerun_extraction",
    "match_and_price",
    "build_proposal",
    "ingest_pricebook",
]
JobStatus = Literal["queued", "running", "done", "failed", "cancelled"]
CostSource = Literal[
    "P21_LAST_PO", "LIST_X_MULTIPLIER", "VENDOR_RFQ", "DISTRIBUTOR_MANUAL", "MANUAL", "BOOK_PRICE"
]
ProductType = Literal[
    "commodity", "restroom_partitions", "specialty", "custom_built", "accessories"
]


class Evidence(BaseModel):
    """Why a line reads the way it does, and where it came from."""

    note: str | None = None
    sheet: str | None = None
    row: int | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    sourceFile: str | None = None
    sourcePage: int | None = None
    bbox: list[float] | None = None
    pageSize: dict[str, float] | None = None


# ── projects ────────────────────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    brand: str | None = None
    jobName: str | None = None
    location: str | None = None
    state: str | None = Field(default=None, max_length=2, description="Ship-to state; drives tax")
    architect: str | None = None
    gc: str | None = None
    initiator: str | None = None
    bidDue: date | None = None
    projectNumber: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    brand: str | None = None
    jobName: str | None = None
    location: str | None = None
    state: str | None = Field(default=None, max_length=2)
    architect: str | None = None
    gc: str | None = None
    initiator: str | None = None
    bidDue: date | None = None
    projectNumber: str | None = None
    stage: Stage | None = None


class Project(ProjectCreate):
    id: str
    code: str
    slug: str
    stage: Stage = "intake"
    progress: int = 0
    createdAt: datetime
    updatedAt: datetime | None = None


# ── documents ───────────────────────────────────────────────────────────────


class Document(BaseModel):
    id: str
    projectId: str
    filename: str
    kind: Literal["plan", "spec", "rfp", "addendum", "other"] = "plan"
    pages: int | None = None
    bytes: int | None = None
    path: str
    state: Literal["received", "reading", "read", "failed"] = "received"
    uploadedAt: datetime


# ── line items ──────────────────────────────────────────────────────────────


class LineItemBase(BaseModel):
    mark: str | None = None
    description: str = ""
    size: str | None = None
    qty: float = 1
    hwSet: str | None = None
    division: str | None = None
    handing: str | None = None
    finish: str | None = None
    fireRating: str | None = None
    frameType: str | None = None
    wallType: str | None = None
    notes: str | None = None


class LineItemCreate(LineItemBase):
    productId: str | None = None
    part: str | None = None


class LineItemUpdate(BaseModel):
    mark: str | None = None
    description: str | None = None
    size: str | None = None
    qty: float | None = None
    hwSet: str | None = None
    division: str | None = None
    handing: str | None = None
    finish: str | None = None
    fireRating: str | None = None
    status: LineStatus | None = None
    notes: str | None = None


class LineItem(LineItemBase):
    id: str
    projectId: str
    status: LineStatus = "needs_look"
    confidence: float | None = None
    flags: list[str] = []
    evidence: Evidence | None = None
    duplicateOf: str | None = None
    duplicateReason: str | None = None
    addedByHand: bool = False
    confirmedBy: str | None = None
    confirmedAt: datetime | None = None
    createdAt: datetime | None = None


# ── quote ───────────────────────────────────────────────────────────────────


class QuoteLineBase(BaseModel):
    part: str | None = None
    description: str = ""
    division: str | None = None
    qty: float = 1
    cost: float | None = None
    margin: float | None = Field(default=None, ge=0.0, lt=1.0)
    productType: ProductType | None = None
    basis: str | None = "Book price"


class QuoteLineCreate(QuoteLineBase):
    lineItemId: str | None = None
    productId: str | None = None


class QuoteLineUpdate(BaseModel):
    description: str | None = None
    qty: float | None = None
    cost: float | None = None
    margin: float | None = Field(default=None, ge=0.0, lt=1.0)
    basis: str | None = None
    overrideReason: str | None = None


class QuoteLine(QuoteLineBase):
    id: str
    projectId: str
    lineItemId: str | None = None
    sell: float | None = None
    extended: float | None = None
    costSource: CostSource | None = None
    costSourceDetail: str | None = None
    multiplier: float | None = None
    multiplierTier: str | None = None
    multiplierEffectiveDate: str | None = None
    priceBookVersion: str | None = None
    sourcePage: int | None = None
    addedByHand: bool = False
    marginOverridden: bool = False
    overrideReason: str | None = None
    priceStatus: str | None = None
    flags: list[str] = []


class QuoteSettings(BaseModel):
    taxJurisdiction: str | None = Field(default=None, description="Two-letter state, e.g. OH")
    freight: float | None = None


class QuoteTotals(BaseModel):
    subtotal: float
    margin: float | None = None
    taxRate: float
    tax: float
    freight: float | None = None
    freightNote: str | None = None
    grandTotal: float
    taxJurisdiction: str | None = None
    taxNote: str | None = None
    groups: list[dict[str, Any]] = []


# ── proposal ────────────────────────────────────────────────────────────────


class ProposalSettings(BaseModel):
    markup: float = Field(default=0.0, ge=0.0, le=0.25)
    customer: dict[str, Any] | None = None
    salesRep: dict[str, Any] | None = None
    estimator: dict[str, Any] | None = None
    exclusions: list[str] | None = None


# ── catalog and price books ─────────────────────────────────────────────────


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
    updatedAt: datetime | None = None
    updatedBy: str | None = None


class PriceBookBase(BaseModel):
    vendor: str = Field(min_length=1)
    program: str | None = None
    multiplier: float | None = None
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


# ── jobs ────────────────────────────────────────────────────────────────────


class JobCreate(BaseModel):
    type: JobType
    projectId: str | None = None
    payload: dict[str, Any] = {}


class Job(BaseModel):
    id: str
    type: JobType
    projectId: str | None = None
    payload: dict[str, Any] = {}
    status: JobStatus = "queued"
    attempts: int = 0
    error: str | None = None
    log: str | None = None
    createdBy: str | None = None
    createdAt: datetime
    startedAt: datetime | None = None
    finishedAt: datetime | None = None


# ── users ───────────────────────────────────────────────────────────────────


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    name: str
    initials: str
    role: str = "estimator"


class Credentials(BaseModel):
    email: EmailStr
    password: str
