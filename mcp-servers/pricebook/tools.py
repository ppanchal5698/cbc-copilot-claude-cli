"""Tool definitions for the pricebook MCP server.

Every result carries source_page and the price-book effective date so a quoted
number can be traced to the sheet it came from (NFR-3).
"""
from __future__ import annotations

from typing import Any

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_vendors",
        "description": (
            "List the indexed vendor price books - vendor, file, effective date, page "
            "count and known multiplier tier. Start here to see what is available."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_product",
        "description": (
            "Fuzzy-search the vendor price books for a product by description, series "
            "or part number. Returns ranked hits with source_page. Narrow with vendor "
            "when you know it - a whole-library search is slow and noisier."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "e.g. '3500 storeroom lock' or '4040XP'"},
                "vendor": {
                    "type": "string",
                    "description": "Optional vendor key from list_vendors, e.g. 'hager'",
                },
                "division": {
                    "type": "string",
                    "description": "Optional '08' or '10' to bias the vendor set",
                },
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "lookup_pricing",
        "description": (
            "Look up the list price for an exact part number and compute net cost as "
            "list x the CBC multiplier tier. Returns every price candidate found on the "
            "page with its source_page - it does not silently pick one when the page is "
            "ambiguous. Adders (electrification, NRP, premium finish) are NOT included; "
            "see reference-library/adders/manual_adders.json"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "part_number": {"type": "string"},
                "vendor": {"type": "string"},
                "category": {
                    "type": "string",
                    "description": (
                        "Multiplier category, e.g. locks / door_controls / exit_devices / "
                        "architectural_hinges. Needed because tiers differ per category."
                    ),
                },
            },
            "required": ["part_number", "vendor"],
        },
    },
    {
        "name": "get_multiplier",
        "description": (
            "Return the CBC multiplier tier for a vendor (and product category where the "
            "vendor prices by category, as Hager does), with its effective date. "
            "Returns null with a note when the tier is unknown - never a guess."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "vendor": {"type": "string"},
                "tier": {
                    "type": "string",
                    "description": "Optional product category or named tier, e.g. 'locks', 'L3'",
                },
            },
            "required": ["vendor"],
        },
    },
]
