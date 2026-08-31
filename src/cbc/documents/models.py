"""Pydantic schemas for document deep-index artifacts."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FieldSchema(BaseModel):
    name: str
    type: str = "string"
    description: str | None = None


class SchemaConfig(BaseModel):
    anchor_pattern: str
    price_or_key_value_regex: str
    code_regex: str
    field_schema: list[FieldSchema] = Field(default_factory=list)
    spans_multiple_pages: bool = False
    notes: str | None = None


class PageExtract(BaseModel):
    page_number: int
    text: str
    visual_page: bool = False


class SectionIndexEntry(BaseModel):
    page_range: list[int]
    section_title: str
    description: str
    tags: list[str] = Field(default_factory=list)
    entities_present: list[str] = Field(default_factory=list)


class SectionExtractionResult(BaseModel):
    page_range: list[int]
    section_title: str
    description: str
    tags: list[str] = Field(default_factory=list)
    entities_present: list[str] = Field(default_factory=list)
    extracted_records: list[dict[str, Any]] = Field(default_factory=list)
    expected_key_value_count: int = 0
    produced_record_count: int = 0


class ReviewItem(BaseModel):
    page_range: list[int]
    section_title: str
    expected_key_value_count: int
    produced_record_count: int
    attempts: int
    reason: str


class Manifest(BaseModel):
    document_id: str
    client_id: str
    document_type: str
    effective_date: str
    source_path: str
    schema_config: SchemaConfig
    total_sections: int = 0
    total_records: int = 0
    review_needed_count: int = 0
    indexing_completed_at: str | None = None
    status: str = "processing"


class DiffEntry(BaseModel):
    entity: str
    change_type: str  # added | removed | changed
    old_value: Any | None = None
    new_value: Any | None = None
    field: str | None = None


class DiffReport(BaseModel):
    from_document_id: str
    to_document_id: str
    client_id: str
    document_type: str
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    changed: list[DiffEntry] = Field(default_factory=list)
    generated_at: str
