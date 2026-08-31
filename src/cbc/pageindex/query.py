"""Finding the page to open.

The whole point of the index: turn "what does a Hager 3400 storeroom lock cost"
into "open PDF page 297" without reading 744 pages, and without trusting a
pre-extracted table that may have misread the row.

Scoring is deliberately explainable. A pricing pass that is sent to the wrong
page must be able to see why, and an estimator reviewing a quote must be able to
follow the same trail. There is no embedding here and nothing to re-train.
"""
from __future__ import annotations

import re
from typing import Any

from cbc.pageindex import store
from cbc.pageindex.models import PageEntry, PageIndexDocument

# Words that match every page of every price book and so separate nothing.
_STOPWORDS = frozenset(
    """a an and or the for of with to in on at by from price prices list cost
    each item items product products series type size finish""".split()
)


def _terms(query: str) -> list[str]:
    return [t for t in re.split(r"[^A-Za-z0-9/-]+", query.upper()) if len(t) > 1]


def _looks_like_code(term: str) -> bool:
    """A part number, as opposed to a word. Digits are the giveaway."""
    return any(ch.isdigit() for ch in term)


def score_page(page: PageEntry, terms: list[str]) -> tuple[float, list[str]]:
    """How well one page answers the query, and why.

    Weighted so a part-number hit beats a description word: "3400" appearing in
    the code families of a page is much stronger evidence than "lock" appearing
    in its prose.
    """
    if not terms:
        return 0.0, []

    title = page.title.upper()
    description = page.description.upper()
    prefixes = [c.upper() for c in page.code_prefixes]
    keywords = " ".join(page.keywords).upper()
    score = 0.0
    why: list[str] = []

    for term in terms:
        if term.lower() in _STOPWORDS:
            continue
        code_hit = any(prefix == term or prefix.startswith(term) for prefix in prefixes)
        if code_hit:
            score += 5.0 if _looks_like_code(term) else 2.0
            why.append(f"{term} in part families")
            continue
        if term in title:
            score += 3.0 if _looks_like_code(term) else 2.0
            why.append(f"{term} in title")
            continue
        if term in keywords:
            # What the page actually sells, which is stronger than prose.
            score += 2.5
            why.append(f"{term} in page keywords")
            continue
        if term in description:
            score += 0.5
            why.append(f"{term} in description")

    # A page that carries prices is the one a pricing pass wants; an item-number
    # listing is where you go to find the code first.
    if score and page.has_prices:
        score += 1.0
    if page.kind == "diagram":
        score *= 0.4
    # A page whose own description is uncertain should not outrank a confident one.
    score *= 0.5 + (page.confidence / 2)
    return round(score, 2), why[:4]


async def find_pages(
    query: str,
    *,
    vendor: str | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    """Pages worth opening for this query, best first."""
    terms = _terms(query)
    if not terms:
        return {"query": query, "count": 0, "pages": [], "note": "give something to search for"}

    documents: list[PageIndexDocument] = []
    for header in await store.list_catalogs(vendor):
        document = await store.get(header["_id"])
        if document:
            documents.append(document)

    hits: list[dict[str, Any]] = []
    for document in documents:
        for page in document.pages:
            score, why = score_page(page, terms)
            if score <= 0:
                continue
            hits.append(
                {
                    "catalog_id": document.catalog_id,
                    "vendor": document.vendor,
                    "file": document.file_name,
                    "pdf_page": page.pdf_page,
                    "printed_page": page.printed_page,
                    "locator": page.locator(),
                    "title": page.title,
                    "description": page.description,
                    "code_prefixes": page.code_prefixes,
                    "keywords": page.keywords,
                    "has_prices": page.has_prices,
                    "kind": page.kind,
                    "price_basis": document.price_basis,
                    "effective_date": document.effective_date,
                    "score": score,
                    "why": why,
                }
            )

    hits.sort(key=lambda h: -h["score"])
    top = hits[:limit]
    return {
        "query": query,
        "count": len(top),
        "total_matched": len(hits),
        "pages": top,
        "note": (
            "Open the page with pdf-tools and read the price off it. These "
            "descriptions route; they do not quote."
            if top
            else "No page matched. That is not proof the part does not exist - it "
                 "may be a MANUAL cut-off item, or in a catalog not indexed yet. "
                 "Do not substitute a similar part."
        ),
    }


async def get_overview(catalog_id: str) -> dict[str, Any]:
    """What this catalog is, before you go looking for a page in it."""
    document = await store.get(catalog_id)
    if document is None:
        return {"found": False, "catalog_id": catalog_id, "note": "no such catalog"}
    return {
        "found": True,
        "catalog_id": document.catalog_id,
        "vendor": document.vendor,
        "file": document.file_name,
        "kind": document.kind,
        "price_basis": document.price_basis,
        "effective_date": document.effective_date,
        "page_count": document.page_count,
        "summary": document.overview.summary,
        "product_lines": document.overview.product_lines,
        "how_prices_are_shown": document.overview.how_prices_are_shown,
        "gotchas": document.overview.gotchas,
        "how_to_find_a_part": document.overview.how_to_find_a_part,
    }


async def get_page(catalog_id: str, pdf_page: int) -> dict[str, Any]:
    """One page's entry, for confirming a citation before quoting it."""
    document = await store.get(catalog_id)
    if document is None:
        return {"found": False, "note": "no such catalog"}
    for page in document.pages:
        if page.pdf_page == pdf_page:
            return {
                "found": True,
                "catalog_id": document.catalog_id,
                "file": document.file_name,
                "pdf_page": page.pdf_page,
                "printed_page": page.printed_page,
                "locator": page.locator(),
                "title": page.title,
                "description": page.description,
                "code_prefixes": page.code_prefixes,
                "has_prices": page.has_prices,
                "kind": page.kind,
                "confidence": page.confidence,
                "price_basis": document.price_basis,
                "effective_date": document.effective_date,
            }
    return {"found": False, "note": f"{catalog_id} has no page {pdf_page}"}
