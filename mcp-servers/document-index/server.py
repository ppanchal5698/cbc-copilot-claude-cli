#!/usr/bin/env python3
"""document-index MCP server — routing and verified section content."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "mcp-servers"))

from _runtime import serve  # noqa: E402
from tools import TOOLS  # noqa: E402

from cbc.documents import search  # noqa: E402


def search_index(
    query: str,
    document_id: str | None = None,
    client_id: str | None = None,
    document_type: str | None = None,
    tag_filter: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    return search.search_index(
        query,
        document_id=document_id,
        client_id=client_id,
        document_type=document_type,
        tag_filter=tag_filter,
        limit=limit,
    )


def get_section_content(
    page_range: list[int],
    document_id: str | None = None,
    client_id: str | None = None,
    document_type: str | None = None,
) -> dict[str, Any]:
    return search.get_section_content(
        page_range,
        document_id=document_id,
        client_id=client_id,
        document_type=document_type,
    )


def get_exact_record(
    code: str,
    document_id: str | None = None,
    client_id: str | None = None,
    document_type: str | None = None,
) -> dict[str, Any]:
    return search.get_exact_record(
        code,
        document_id=document_id,
        client_id=client_id,
        document_type=document_type,
    )


def list_document_versions(client_id: str, document_type: str) -> dict[str, Any]:
    return search.list_document_versions(client_id, document_type)


HANDLERS = {
    "search_index": search_index,
    "get_section_content": get_section_content,
    "get_exact_record": get_exact_record,
    "list_document_versions": list_document_versions,
}

_FORBIDDEN = ("write", "update", "insert", "upsert", "delete", "create", "set_")
assert not [t for t in TOOLS if any(word in t["name"].lower() for word in _FORBIDDEN)]


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        serve("document-index", TOOLS, HANDLERS)
    else:
        serve("document-index", TOOLS, HANDLERS)
