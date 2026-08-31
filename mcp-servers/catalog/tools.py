"""Tool definitions for the catalog MCP server.

READ-ONLY, over the SQLite FTS5 index built from the vendor PDFs. A pricing pass
searches the index; it never opens a price book. Reading them on every query cost
6 s cold and 2.5 s warm per search, and a fresh MCP process per run paid it again
every time.

Every result carries the vendor, the source file and the page number, so a quoted
number traces back to the sheet it was read from (NFR-3).
"""
from __future__ import annotations

from typing import Any

_LIMIT = {"type": "integer", "default": 10, "minimum": 1, "maximum": 50}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_products",
        "description": (
            "Search every indexed vendor catalog by part number, series, or plain "
            "description. An exact part-number match ranks first and is never left to "
            "fuzzy matching. Narrow with vendor when you know it. Returns price, unit, "
            "source file and page number for each hit. Milliseconds - use it freely."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "'150CX18', 'B-2888', '3500 storeroom lock', 'grab bar'",
                },
                "vendor": {"type": "string", "description": "e.g. 'hager', 'bobrick'"},
                "catalog_id": {"type": "string", "description": "Restrict to one catalog"},
                "category": {"type": "string"},
                "limit": _LIMIT,
                "offset": {"type": "integer", "default": 0, "minimum": 0},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_product_details",
        "description": (
            "One product in full, with the raw text it was extracted from and the "
            "catalog it belongs to. Use it to check a match before pricing a line."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer"},
                "product_code": {"type": "string"},
                "vendor": {"type": "string", "description": "Disambiguates a shared part number"},
            },
        },
    },
    {
        "name": "search_catalog",
        "description": "Search inside one catalog. Same ranking, scoped to that book.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "catalog_id": {"type": "string"},
                "query": {"type": "string"},
                "limit": _LIMIT,
            },
            "required": ["catalog_id", "query"],
        },
    },
    {
        "name": "list_catalogs",
        "description": (
            "Every catalog in the index: vendor, status, product count, effective date "
            "and how stale it is. Start here to see what is searchable - a catalog that "
            "is not 'ready' is not in the results."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"vendor": {"type": "string"}},
        },
    },
    {
        "name": "get_catalog_status",
        "description": (
            "Where one catalog is in its lifecycle: uploaded, queued, processing, "
            "indexing, ready, failed or deleting - with the reason when it failed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"catalog_id": {"type": "string"}},
            "required": ["catalog_id"],
        },
    },
    {
        "name": "get_multiplier",
        "description": (
            "The CBC multiplier tier for a vendor, from the curated tier sheet - not "
            "extracted from a PDF. Returns null and says so rather than guessing when "
            "the vendor is not on file."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "vendor": {"type": "string"},
                "category": {
                    "type": "string",
                    "description": "e.g. locks / door_controls / exit_devices",
                },
            },
            "required": ["vendor"],
        },
    },
    # ── kept for the agents and skills that already call them ───────────────
    {
        "name": "search_product",
        "description": (
            "Alias of search_products, kept so existing agents and skills keep working. "
            "Prefer search_products."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "vendor": {"type": "string"},
                "division": {"type": "string"},
                "limit": _LIMIT,
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_vendors",
        "description": "Alias of list_catalogs, grouped by vendor. Prefer list_catalogs.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "lookup_pricing",
        "description": (
            "List price for an exact part number, and net cost. Special net items from "
            "the multiplier sheet override list × category when present. Reads the index, "
            "not the PDF. Returns every candidate it found with its page - it does not pick "
            "one when the answer is ambiguous. Adders (electrification, NRP, premium finish) "
            "are NOT included; see reference-library/adders/manual_adders.json"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "part_number": {"type": "string"},
                "vendor": {"type": "string"},
                "category": {"type": "string", "description": "Multiplier category"},
            },
            "required": ["part_number", "vendor"],
        },
    },
    {
        "name": "get_special_net",
        "description": (
            "Fixed net price from a vendor multiplier sheet when the part appears on the "
            "special nets pages. Hager only today. Returns null when no override exists."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "vendor": {"type": "string"},
                "part_number": {"type": "string"},
            },
            "required": ["vendor", "part_number"],
        },
    },
    {
        "name": "is_stock_item",
        "description": (
            "Whether a part is on the NR-6 top-10 stock list for a vendor. Returns null "
            "when no curated list is on file yet."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "vendor": {"type": "string"},
                "part_number": {"type": "string"},
            },
            "required": ["vendor", "part_number"],
        },
    },
]
