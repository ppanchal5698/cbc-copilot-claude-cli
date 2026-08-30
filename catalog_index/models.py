"""What an extractor produces and what a search returns.

`code_norm` is the point of this module. An estimator types `b2888`, the drawing
says `B-2888` and the price book prints `B 2888`; all three are the same part and
all three normalize to `B2888`. Exact identifier lookup runs against that column,
not against fuzzy text - a part number is not a phrase to be approximately matched.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_NON_CODE = re.compile(r"[^A-Z0-9]")
_HAS_DIGIT = re.compile(r"\d")


def normalize_code(text: str | None) -> str | None:
    """Upper-case, strip everything that is not alphanumeric."""
    if not text:
        return None
    stripped = _NON_CODE.sub("", text.upper())
    return stripped or None


def looks_like_code(text: str) -> bool:
    """Is this query plausibly a part number rather than a description?

    Deliberately conservative: a single token, at least three characters, and
    containing a digit. "hinge" is not a code; "150CX18" and "B-2888" are.
    """
    token = text.strip()
    if not token or " " in token:
        return False
    normalized = normalize_code(token)
    return bool(normalized and len(normalized) >= 3 and _HAS_DIGIT.search(normalized))


@dataclass(slots=True)
class ProductRecord:
    """One product as read off one page of one catalog.

    `page_number` and `raw_text` are not optional extras: NFR-3 requires every
    quoted line to trace to a source page, and `raw_text` is what makes a bad
    parse auditable instead of merely wrong.
    """

    vendor: str
    page_number: int
    product_code: str | None = None
    name: str | None = None
    description: str | None = None
    category: str | None = None
    price: float | None = None
    unit: str | None = None
    raw_text: str | None = None

    @property
    def code_norm(self) -> str | None:
        return normalize_code(self.product_code)

    def as_row(self, catalog_id: str, version: int, build_id: str) -> tuple[Any, ...]:
        return (
            build_id,
            catalog_id,
            version,
            self.vendor,
            self.product_code,
            self.code_norm,
            self.name,
            self.description,
            self.category,
            self.price,
            self.unit,
            self.page_number,
            self.raw_text,
        )


@dataclass(slots=True)
class ExtractionResult:
    """What one adapter made of one file, and how much of it it had to throw away."""

    records: list[ProductRecord] = field(default_factory=list)
    extractor: str = "unknown"
    pages_read: int = 0
    rejected: dict[str, int] = field(default_factory=dict)

    @property
    def validation_rate(self) -> float:
        """Kept rows as a fraction of rows considered. 1.0 when nothing was seen."""
        thrown_away = sum(self.rejected.values())
        seen = len(self.records) + thrown_away
        return 1.0 if seen == 0 else len(self.records) / seen
