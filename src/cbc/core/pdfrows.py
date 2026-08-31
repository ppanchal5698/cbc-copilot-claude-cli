"""Recovering rows from a PDF page, and repairing text that decodes as noise.

Two pieces of hard-won machinery live here, shared by the pdf-tools MCP server
(which reads bid sets) and the catalog index (which reads price books). They are
shared rather than copied because if the two ever disagreed about what a page says,
a quoted price would not match the drawing it was checked against.

**Glyph repair.** Some CAD and vendor exports embed fonts with no usable ToUnicode
map, so raw glyph codes come through instead of characters: "DO NOT SCALE DRAWINGS"
extracts as "'2\\x03127\\x036&$/(". The codes are offset from ASCII by a constant, so
the text is recoverable - but only if something notices. Nothing did, and on the
first real bid set it cost an entire run.

**Row clustering.** A CAD sheet places every label as a free-floating text run;
there are no table rules to detect. Rows are recovered geometrically, and every row
and cell keeps its bounding box so a reviewer can be shown the exact spot a value
was read from (NFR-3).
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

ROW_TOLERANCE = 6.0  # points; two words within this vertical distance share a row
COLUMN_GAP = 12.0  # points; a horizontal gap wider than this starts a new cell

_CONTROL_THRESHOLD = 0.05  # below this the text is already sound; leave it alone
_MAX_SHIFT = 64
_SHIFT_CACHE: dict[tuple[str, float], int] = {}

# Words a set of architectural drawings or a vendor price book is near-certain to
# contain. Scoring on letter count alone picks a shift that turns everything into
# lowercase gibberish, because gibberish has more letters than real text has.
_ANCHOR_WORDS = frozenset(
    """the and not use all wall door type plan scale with shall dimension room floor
    detail sheet schedule general notes frame section existing new provide contractor
    architect finish equipment mounted typical above below required price list net
    each series stainless steel satin mounted surface""".split()
)
_WORD_RE = re.compile(r"[A-Za-z]{2,}")


def control_ratio(text: str) -> float:
    if not text:
        return 0.0
    return sum(1 for c in text if ord(c) < 32 and c not in "\n\r\t") / len(text)


def english_score(text: str) -> float:
    """How much this reads like real document text, rather than merely like letters."""
    words = [w.lower() for w in _WORD_RE.findall(text)]
    if not words:
        return 0.0
    return sum(1 for w in words if w in _ANCHOR_WORDS) / len(words) ** 0.5


def shift_text(text: str, shift: int) -> str:
    """Offset glyph codes back to characters, leaving the layout alone.

    Newlines, returns and tabs are real structure, not glyph codes - shifting a
    newline by 29 turns it into an apostrophe and welds every line of the sheet
    into one, which destroys the row structure the parser depends on.
    """
    if not shift:
        return text
    return "".join(
        c
        if c in "\n\r\t"
        else (chr(ord(c) + shift) if 32 <= ord(c) + shift < 127 else c)
        for c in text
    )


def detect_shift(doc: fitz.Document, file_path: str) -> int:
    """The document-wide glyph offset, or 0 when the text needs no repair.

    Decided once per document from a sample of pages. Per-page detection is
    noisier - a sheet that is mostly dimensions carries too few words to score.
    """
    key = (file_path, Path(file_path).stat().st_mtime if Path(file_path).exists() else 0.0)
    if key in _SHIFT_CACHE:
        return _SHIFT_CACHE[key]

    sample = "".join(doc[i].get_text()[:4000] for i in range(min(6, doc.page_count)))
    shift = 0
    if control_ratio(sample) > _CONTROL_THRESHOLD:
        best = english_score(sample)
        for candidate in range(1, _MAX_SHIFT + 1):
            score = english_score(shift_text(sample, candidate))
            if score > best:
                best, shift = score, candidate

    _SHIFT_CACHE[key] = shift
    return shift


def union_bbox(words: list[tuple]) -> list[float]:
    """Union bounding box of a group of words, as [x0, y0, x1, y1] in PDF points."""
    return [
        round(min(w[0] for w in words), 2),
        round(min(w[1] for w in words), 2),
        round(max(w[2] for w in words), 2),
        round(max(w[3] for w in words), 2),
    ]


def rows_from_words(
    page: fitz.Page, region: list[float] | None = None, shift: int = 0
) -> list[dict[str, Any]]:
    """Cluster positioned words into rows of cells."""
    words = page.get_text("words")  # (x0, y0, x1, y1, word, block, line, word_no)
    if shift:
        words = [(*w[:4], shift_text(w[4], shift), *w[5:]) for w in words]
    if region:
        x0, y0, x1, y1 = region
        words = [w for w in words if x0 <= w[0] <= x1 and y0 <= w[1] <= y1]
    if not words:
        return []

    buckets: dict[int, list[tuple]] = defaultdict(list)
    for word in words:
        buckets[int(word[1] // ROW_TOLERANCE)].append(word)

    rows: list[dict[str, Any]] = []
    for key in sorted(buckets):
        line = sorted(buckets[key], key=lambda w: w[0])
        cells: list[list[tuple]] = [[line[0]]]
        for word in line[1:]:
            if word[0] - cells[-1][-1][2] > COLUMN_GAP:
                cells.append([word])
            else:
                cells[-1].append(word)
        rows.append(
            {
                "y": round(line[0][1], 1),
                "x_start": round(line[0][0], 1),
                "bbox": union_bbox(line),
                "cells": [" ".join(w[4] for w in cell) for cell in cells],
                "cell_boxes": [union_bbox(cell) for cell in cells],
                "text": " | ".join(" ".join(w[4] for w in cell) for cell in cells),
            }
        )
    return rows


def ocr_page(page: fitz.Page, dpi: int = 300) -> str:
    """OCR fallback. Optional: returns a clear marker when pytesseract is unavailable."""
    try:
        import io

        import pytesseract
        from PIL import Image
    except ImportError:
        return (
            "[OCR UNAVAILABLE - install pytesseract and the tesseract binary "
            "to read scanned pages]"
        )
    pixmap = page.get_pixmap(dpi=dpi)
    image = Image.open(io.BytesIO(pixmap.tobytes("png")))
    try:
        return str(pytesseract.image_to_string(image))
    except Exception as exc:  # tesseract binary missing or failed
        return f"[OCR FAILED: {exc}]"


def has_text_layer(page: fitz.Page, minimum_chars: int = 40) -> bool:
    """Is there real text here, or is this a scan that will need OCR?"""
    return len(page.get_text().strip()) >= minimum_chars
