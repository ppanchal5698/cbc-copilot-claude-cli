"""What is worth indexing, and what is page furniture.

A price book page is mostly not products. It is headers, footers, page numbers,
effective dates, column titles, footnotes and legal boilerplate - and a parser that
indexes all of it produces a search where every query matches "PRICE LIST 2026".

Rejections are counted rather than silently dropped, because the count is the
signal: a vendor whose sheet suddenly yields a 10% validation rate has changed its
layout, and that should fail the catalog loudly rather than quietly index noise
(NFR-2 - flag what you cannot determine, never guess).
"""
from __future__ import annotations

import re
from collections import Counter

from catalog_index.models import ProductRecord

# A price that is really a year, a page number or a phone number.
MIN_PRICE = 0.01
MAX_PRICE = 1_000_000.0
_YEARS = range(1900, 2100)

_CODE_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .\-/#]{1,39}$")
_MOSTLY_PUNCT = re.compile(r"^[^A-Za-z0-9]*$")

# A row seen on this many pages is a running header or footer, not a product.
REPEAT_THRESHOLD = 5


def _is_noise(text: str | None) -> bool:
    if not text:
        return True
    stripped = text.strip()
    if len(stripped) < 2 or _MOSTLY_PUNCT.match(stripped):
        return True
    # OCR noise: mostly non-alphanumeric characters once spaces are removed.
    dense = stripped.replace(" ", "")
    if not dense:
        return True
    alnum = sum(c.isalnum() for c in dense)
    return alnum / len(dense) < 0.5


def valid_price(price: float | None) -> bool:
    if price is None:
        return True  # an honestly unpriced row is still a product
    if not MIN_PRICE <= price <= MAX_PRICE:
        return False
    # A bare 2026 in a price column is the effective date, not a cost.
    return not (price.is_integer() and int(price) in _YEARS)


def clean(records: list[ProductRecord]) -> tuple[list[ProductRecord], dict[str, int]]:
    """Keep the rows that are products. Report what went and why."""
    rejected: Counter[str] = Counter()

    # Rows whose text repeats across many pages are running headers/footers.
    seen_on_pages: dict[str, set[int]] = {}
    for record in records:
        key = (record.name or record.raw_text or "").strip().lower()
        if key:
            seen_on_pages.setdefault(key, set()).add(record.page_number)
    repeated = {k for k, pages in seen_on_pages.items() if len(pages) >= REPEAT_THRESHOLD}

    kept: list[ProductRecord] = []
    already: set[tuple[str | None, int]] = set()

    for record in records:
        label = (record.name or record.raw_text or "").strip().lower()

        if _is_noise(record.name) and _is_noise(record.description):
            rejected["unreadable"] += 1
            continue
        if label in repeated:
            rejected["running_header_or_footer"] += 1
            continue
        if record.product_code and not _CODE_OK.match(record.product_code.strip()):
            rejected["implausible_code"] += 1
            continue
        if not valid_price(record.price):
            rejected["implausible_price"] += 1
            continue

        identity = (record.code_norm, record.page_number)
        if record.code_norm and identity in already:
            rejected["duplicate_on_page"] += 1
            continue
        already.add(identity)
        kept.append(record)

    return kept, dict(rejected)
