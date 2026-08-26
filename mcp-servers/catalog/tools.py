"""Tool definitions for the catalog MCP server.

READ-ONLY. The estimator and the ingest job own writes; a pricing pass reads.
This is how Claude sees the newest catalog and multiplier data automatically -
it queries the live database rather than a snapshot on disk.
"""
from __future__ import annotations

from typing import Any

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_products",
        "description": (
            "Search the live product catalog by part number, description or "
            "manufacturer. Part-number matches rank first. Returns cost, list "
            "price, multiplier and the price book each figure came from."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Part number, series or keywords"},
                "division": {"type": "string", "description": "e.g. '08 11 00' or '10 28 00'"},
                "manufacturer": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_product",
        "description": (
            "Fetch one catalog part by exact part number, with its price book, "
            "multiplier tier and cross-references to equivalent parts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"part": {"type": "string"}},
            "required": ["part"],
        },
    },
    {
        "name": "get_multiplier",
        "description": (
            "Current multiplier tier for a vendor, and the product category when "
            "the vendor prices by category as Hager does. Returns null with a "
            "note when the tier is unknown - never a guess."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "vendor": {"type": "string"},
                "category": {
                    "type": "string",
                    "description": "e.g. locks, door_controls, exit_devices, architectural_hinges",
                },
            },
            "required": ["vendor"],
        },
    },
    {
        "name": "list_price_books",
        "description": (
            "Every price book and multiplier program purchasing maintains, with "
            "its effective date and how stale it is. Check this before trusting "
            "a cost - NFR-10 has no named owner yet, so age is the only signal."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "vendor": {"type": "string", "description": "Optional vendor filter"}
            },
        },
    },
]
