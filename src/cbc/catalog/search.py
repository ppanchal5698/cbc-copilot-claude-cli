"""Searching the index.

One entry point, used by the API and by the MCP server, so an estimator typing into
the catalog screen and a pricing pass calling a tool get the same answer.

Two tiers, in this order:

  1. **Exact identifier.** A query that looks like a part number is looked up on the
     normalized code column, which is indexed. `B-2888`, `b2888` and `B 2888` all
     find the same row. A part number is an identifier, not a phrase, and leaving it
     to fuzzy ranking is how "the nearest stock part" ends up on a quote (NFR-2).
  2. **Full text.** bm25 over FTS5, weighted so a hit in the product code outranks a
     hit in a description.

The FTS query is built from tokens, never from raw input. MATCH is a query language:
an unescaped `"` is a syntax error and an unescaped `*` or `NEAR` silently means
something the estimator did not ask for - the same class of bug as an unescaped
regex reaching the database.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any

from cbc.catalog.models import looks_like_code, normalize_code

DEFAULT_LIMIT = 20
MAX_LIMIT = 100

# bm25 weights, one per FTS column: product_code, name, description, category, vendor.
# A part number matching the code column is worth far more than the same string
# appearing in prose.
WEIGHTS = (10.0, 5.0, 1.0, 1.0, 1.0)

_TOKEN = re.compile(r"[\w#./-]+", re.UNICODE)

_SELECT = """
    SELECT p.id, p.catalog_id, p.vendor, p.product_code, p.code_norm, p.name,
           p.description, p.category, p.price, p.unit, p.page_number,
           c.file_name, c.effective_date
"""


def build_match(query: str, *, prefix: bool = True) -> str:
    """Turn free text into a safe FTS5 MATCH expression.

    Every token is wrapped as a quoted string with internal quotes doubled, so no
    input can be read as FTS syntax. The final token gets a `*` so typing keeps
    narrowing results as the estimator goes.
    """
    tokens = _TOKEN.findall(query or "")
    if not tokens:
        return ""
    quoted = ['"' + token.replace('"', '""') + '"' for token in tokens]
    if prefix:
        quoted[-1] += "*"
    return " AND ".join(quoted)


def _filters(vendor: str | None, catalog_id: str | None, category: str | None) -> tuple[str, list]:
    clauses, params = ["c.status = 'ready'"], []
    if vendor:
        clauses.append("lower(p.vendor) = lower(?)")
        params.append(vendor)
    if catalog_id:
        clauses.append("p.catalog_id = ?")
        params.append(catalog_id)
    if category:
        clauses.append("lower(p.category) = lower(?)")
        params.append(category)
    return " AND ".join(clauses), params


def _row(record: sqlite3.Row, score: float) -> dict[str, Any]:
    return {
        "product_id": record["id"],
        "catalog_id": record["catalog_id"],
        "vendor": record["vendor"],
        "product_name": record["name"],
        "product_code": record["product_code"],
        "description": record["description"],
        "category": record["category"],
        "price": record["price"],
        "unit": record["unit"],
        "source_file": record["file_name"],
        "page_number": record["page_number"],
        "effective_date": record["effective_date"],
        "relevance_score": round(score, 4),
        "also_on_pages": [],
    }


def _relevance(bm25_score: float) -> float:
    """bm25() is negative and lower is better. Map it onto 0..1, best first."""
    return 1.0 / (1.0 + max(0.0, -bm25_score)) if bm25_score < 0 else 0.0


def search(
    connection: sqlite3.Connection,
    query: str,
    *,
    vendor: str | None = None,
    catalog_id: str | None = None,
    category: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """Find products. Never touches a PDF."""
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))
    where, params = _filters(vendor, catalog_id, category)

    results: list[dict[str, Any]] = []
    seen: dict[tuple[str, str | None], dict[str, Any]] = {}

    def collect(record: sqlite3.Row, score: float) -> None:
        key = (record["vendor"].lower(), record["code_norm"])
        existing = seen.get(key) if record["code_norm"] else None
        if existing is not None:
            # Same part, another page. Keep the best-ranked hit and say where else
            # it appears rather than filling the page with near-duplicates.
            page = record["page_number"]
            if page not in existing["also_on_pages"] and page != existing["page_number"]:
                existing["also_on_pages"].append(page)
            return
        row = _row(record, score)
        if record["code_norm"]:
            seen[key] = row
        results.append(row)

    # ── tier 1: exact identifier ────────────────────────────────────────────
    if looks_like_code(query):
        exact = connection.execute(
            f"{_SELECT} FROM products p JOIN catalogs c ON c.catalog_id = p.catalog_id "
            f"WHERE p.code_norm = ? AND {where} ORDER BY p.page_number LIMIT ?",
            [normalize_code(query), *params, limit * 4],
        ).fetchall()
        for record in exact:
            collect(record, 1.0)

    # ── tier 2: full text ───────────────────────────────────────────────────
    match = build_match(query)
    if vendor:
        # Pushed into MATCH rather than filtered afterwards. As a WHERE clause it
        # ran *after* the ranked LIMIT, so a vendor-filtered search could come back
        # short simply because the best global hits belonged to someone else.
        match = f'vendor:"{vendor.replace(chr(34), chr(34) * 2)}"' + (f" AND ({match})" if match else "")
    if category:
        match = f'category:"{category.replace(chr(34), chr(34) * 2)}"' + (f" AND ({match})" if match else "")

    if match and len(results) < offset + limit:
        # Rank first, join second. Ranking inside the join made SQLite compute
        # bm25 across the whole matched set before it could apply the LIMIT:
        # 472 ms for a one-word search, against 0.2 ms this way.
        rows = connection.execute(
            "WITH hits AS ("
            "  SELECT rowid AS pid, bm25(products_fts, ?, ?, ?, ?, ?) AS rank"
            "  FROM products_fts WHERE products_fts MATCH ? ORDER BY rank LIMIT ?"
            ")"
            f"{_SELECT}, hits.rank FROM hits "
            "JOIN products p ON p.id = hits.pid "
            "JOIN catalogs c ON c.catalog_id = p.catalog_id "
            f"WHERE {where} ORDER BY hits.rank",
            [*WEIGHTS, match, (offset + limit) * 5, *params],
        ).fetchall()
        for record in rows:
            collect(record, _relevance(record["rank"]))

    window = results[offset : offset + limit]
    return {
        "query": query,
        "count": len(window),
        "total_matched": len(results),
        "results": window,
        "note": (
            "Nothing in the index matches. That is not proof the part does not exist - "
            "it may be a MANUAL cut-off item, or its catalog may not be indexed yet. "
            "Do not substitute the nearest stock part."
            if not window
            else None
        ),
    }


def get_product(
    connection: sqlite3.Connection,
    *,
    product_id: int | None = None,
    vendor: str | None = None,
    product_code: str | None = None,
) -> dict[str, Any] | None:
    """One product with its full provenance."""
    if product_id is not None:
        record = connection.execute(
            f"{_SELECT}, c.status, c.indexed_at, p.raw_text FROM products p "
            "JOIN catalogs c ON c.catalog_id = p.catalog_id WHERE p.id = ?",
            [product_id],
        ).fetchone()
    elif product_code:
        clause = "p.code_norm = ?"
        params: list[Any] = [normalize_code(product_code)]
        if vendor:
            clause += " AND lower(p.vendor) = lower(?)"
            params.append(vendor)
        record = connection.execute(
            f"{_SELECT}, c.status, c.indexed_at, p.raw_text FROM products p "
            f"JOIN catalogs c ON c.catalog_id = p.catalog_id WHERE {clause} "
            "ORDER BY p.page_number LIMIT 1",
            params,
        ).fetchone()
    else:
        raise ValueError("give either product_id, or product_code (optionally with vendor)")

    if record is None:
        return None
    detail = _row(record, 1.0)
    detail["raw_text"] = record["raw_text"]
    detail["catalog_status"] = record["status"]
    detail["indexed_at"] = record["indexed_at"]
    return detail


def list_catalogs(connection: sqlite3.Connection, vendor: str | None = None) -> list[dict[str, Any]]:
    clause, params = ("WHERE lower(vendor) = lower(?)", [vendor]) if vendor else ("", [])
    rows = connection.execute(
        "SELECT catalog_id, vendor, file_name, status, product_count, version, "
        "effective_date, extractor, indexed_at, error "
        f"FROM catalogs {clause} ORDER BY vendor, file_name",
        params,
    ).fetchall()
    return [dict(row) for row in rows]
