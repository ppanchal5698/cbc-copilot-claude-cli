"""Pydantic schemas grouped by domain."""
from api.schemas.catalog import (
    PriceBook,
    PriceBookBase,
    PriceBookCreate,
    PriceBookUpdate,
    Product,
    ProductBase,
    ProductCreate,
    ProductUpdate,
)
from api.schemas.common import (
    CallKind,
    CostSource,
    Evidence,
    JobStatus,
    JobType,
    LineStatus,
    ProductType,
    Stage,
)
from api.schemas.documents import Document
from api.schemas.jobs import Job, JobCreate
from api.schemas.line_items import BulkAction, LineItem, LineItemCreate, LineItemUpdate
from api.schemas.projects import Project, ProjectCreate, ProjectUpdate
from api.schemas.quote import (
    HandOff,
    ProposalSettings,
    QuoteLine,
    QuoteLineCreate,
    QuoteLineUpdate,
    QuoteSettings,
    QuoteTotals,
)
from api.schemas.users import Call, CallCreate, Credentials, UserCreate, UserPublic, UserUpdate
from api.schemas.versions import AlternateCreate, AlternateAssign, EstimateVersion, VersionCreate

__all__ = [
    "AlternateCreate",
    "AlternateAssign",
    "BulkAction",
    "Call",
    "CallCreate",
    "CallKind",
    "CostSource",
    "Credentials",
    "Document",
    "EstimateVersion",
    "Evidence",
    "HandOff",
    "Job",
    "JobCreate",
    "JobStatus",
    "JobType",
    "LineItem",
    "LineItemCreate",
    "LineItemUpdate",
    "LineStatus",
    "PriceBook",
    "PriceBookBase",
    "PriceBookCreate",
    "PriceBookUpdate",
    "Product",
    "ProductBase",
    "ProductCreate",
    "ProductType",
    "ProductUpdate",
    "Project",
    "ProjectCreate",
    "ProjectUpdate",
    "ProposalSettings",
    "QuoteLine",
    "QuoteLineCreate",
    "QuoteLineUpdate",
    "QuoteSettings",
    "QuoteTotals",
    "Stage",
    "UserPublic",
    "UserCreate",
    "UserUpdate",
    "VersionCreate",
]
