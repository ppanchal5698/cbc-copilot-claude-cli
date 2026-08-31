"""Tool definitions for the document-index MCP server.

READ-ONLY routing over pre-built deep indexes. search_index returns page ranges
only; get_section_content is the sole source for verified records (NFR-3).
"""
from __future__ import annotations

from typing import Any

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_index",
        "description": (
            "Full-text search over deep-index routing metadata (description, tags, "
            "entities_present). Returns page_range and section_title only — not "
            "extracted records. Prefer this over pdf-tools when list_document_versions "
            "shows status ready."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "client_id": {"type": "string", "description": "vendor or project slug"},
                "document_type": {"type": "string", "description": "price_book, multiplier_sheet, plan"},
                "query": {"type": "string"},
                "tag_filter": {"type": "string"},
                "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_section_content",
        "description": (
            "Fetch verified raw text and extracted_records for a page_range from "
            "content.db. This is the ONLY tool whose output may be used in a final answer."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "client_id": {"type": "string"},
                "document_type": {"type": "string"},
                "page_range": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 2,
                    "maxItems": 2,
                },
            },
            "required": ["page_range"],
        },
    },
    {
        "name": "get_exact_record",
        "description": (
            "Direct lookup by product code or entity. Skips fuzzy search — use whenever "
            "the query includes an exact code/SKU."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "client_id": {"type": "string"},
                "document_type": {"type": "string"},
                "code": {"type": "string"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "list_document_versions",
        "description": (
            "All indexed versions for a client_id + document_type, with current_version "
            "pointer. Call first to avoid stale data."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "document_type": {"type": "string"},
            },
            "required": ["client_id", "document_type"],
        },
    },
]
