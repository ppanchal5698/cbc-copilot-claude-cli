#!/usr/bin/env python3
"""pdf-tools MCP server - PDF text, tables, page images and search.

Every result carries source_page (1-indexed) so any extracted value can be traced
back to the drawing it came from (NFR-3, .claude/rules/auditability.md).

Architectural bid sets are CAD exports: a single sheet can carry >13,000 vector
line segments, so ruling-based table detection returns mostly noise. extract_tables
therefore clusters positioned words into rows instead. See
.claude/skills/extract-door-schedule/references/schedule_anatomy.md
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _runtime import serve  # noqa: E402
from tools import TOOLS  # noqa: E402

ROW_TOLERANCE = 6.0  # points; two words within this vertical distance share a row
COLUMN_GAP = 12.0  # points; a horizontal gap wider than this starts a new cell
MAX_HITS = 200

# Budget guards.
#
# `extract_tables(page_range="all")` on a 28-page CAD set returns 1.5 million
# characters - roughly 385,000 tokens in a single tool call, a third of a context
# window spent before any estimating happens. A caller cannot know that in
# advance, so the tool has to bound it and say what it withheld.
#
# Nothing is dropped silently: the response names the pages it did not read and
# how to ask for them. Truncating a schedule without saying so would put missing
# openings into a quote.
MAX_TABLE_PAGES = 4
MAX_ROWS_PER_PAGE = 300

# What a Division 8/10 take-off is looking for on an architectural set.
DEFAULT_SHEET_TERMS = [
    "door schedule",
    "door",
    "frame",
    "hardware",
    "opening",
    "finish schedule",
    "partition",
    "toilet",
    "restroom",
    "accessor",
    "frp",
    "wall type",
]

# ── glyph-code repair ───────────────────────────────────────────────────────
#
# Some CAD exports embed fonts with no usable ToUnicode map, so the raw glyph
# codes come through instead of characters: a sheet note reading "DO NOT SCALE
# DRAWINGS" extracts as "'2\x03127\x036&$/(". The codes are offset from ASCII by a
# constant, so the text is recoverable - but only if something notices.
#
# Nothing did. On the first real bid set this cost an entire run: the model
# rediscovered the offset by hand, one Bash call at a time, and never got a clean
# schedule out of it. Detecting it once per document is the whole fix.
#
# The repair is reported on every result rather than applied silently, because a
# transformed drawing value that nobody can see was transformed is exactly what
# the accuracy rule exists to prevent (NFR-2).

_CONTROL_THRESHOLD = 0.05  # below this the text is already sound; leave it alone
_MAX_SHIFT = 64
_SHIFT_CACHE: dict[tuple[str, float], int] = {}

# Words a set of architectural drawings is near-certain to contain.
_ANCHOR_WORDS = frozenset(
    """the and not use all wall door type plan scale with shall dimension room floor
    detail sheet schedule general notes frame section existing new provide contractor
    architect finish equipment mounted typical above below required""".split()
)
_WORD_RE = re.compile(r"[A-Za-z]{2,}")


def _control_ratio(text: str) -> float:
    if not text:
        return 0.0
    return sum(1 for c in text if ord(c) < 32 and c not in "\n\r\t") / len(text)



def _english_score(text: str) -> float:
    """How much this reads like drawing text, rather than merely like letters.

    Scoring on letter count alone picks a shift that turns everything into
    lowercase gibberish, because gibberish has more letters than real text has.
    Anchoring on words that actually appear on drawings is what separates
    "DO NOT SCALE DRAWINGS" from "ep!opu!tdbmf!esbxjoht".
    """
    words = [w.lower() for w in _WORD_RE.findall(text)]
    if not words:
        return 0.0
    return sum(1 for w in words if w in _ANCHOR_WORDS) / len(words) ** 0.5


def _shift_text(text: str, shift: int) -> str:
    """Offset glyph codes back to characters, leaving the layout alone.

    Newlines, returns and tabs are real structure, not glyph codes - shifting
    a newline by 29 turns it into an apostrophe and welds every line of the
    sheet into one, which destroys the row structure the schedule parser
    depends on.
    """
    if not shift:
        return text
    return "".join(
        c
        if c in "\n\r\t"
        else (chr(ord(c) + shift) if 32 <= ord(c) + shift < 127 else c)
        for c in text
    )


def _detect_shift(doc: fitz.Document, file_path: str) -> int:
    """The document-wide glyph offset, or 0 when the text needs no repair.

    Decided once per document from a sample of pages. Per-page detection is
    noisier - a sheet that is mostly dimensions carries too few words to score.
    """
    key = (file_path, Path(file_path).stat().st_mtime if Path(file_path).exists() else 0.0)
    if key in _SHIFT_CACHE:
        return _SHIFT_CACHE[key]

    sample = "".join(doc[i].get_text()[:4000] for i in range(min(6, doc.page_count)))
    shift = 0
    if _control_ratio(sample) > _CONTROL_THRESHOLD:
        best = _english_score(sample)
        for candidate in range(1, _MAX_SHIFT + 1):
            score = _english_score(_shift_text(sample, candidate))
            if score > best:
                best, shift = score, candidate

    _SHIFT_CACHE[key] = shift
    return shift


def _open(file_path: str) -> fitz.Document:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")
    return fitz.open(path)


def _parse_pages(doc: fitz.Document, spec: str | None) -> list[int]:
    """Return 0-indexed page numbers from a page-range spec such as 1-30, 14 or all."""
    if not spec or spec.strip().lower() == "all":
        return list(range(doc.page_count))
    out: list[int] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if "-" in chunk:
            low, high = chunk.split("-", 1)
            out.extend(range(int(low) - 1, min(int(high), doc.page_count)))
        elif chunk:
            out.append(int(chunk) - 1)
    return [p for p in out if 0 <= p < doc.page_count]


def _ocr_page(page: fitz.Page, dpi: int = 300) -> str:
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


def extract_text(
    file_path: str, pages: list[int] | str | None = None
) -> dict[str, Any]:
    """Text per page, with the glyph offset repaired when the fonts need it.

    `pages` takes a list of 1-indexed numbers or the same spec string
    extract_tables uses ("6", "1-30", "all"). It used to accept only a list and
    raised a TypeError on a string, which is the obvious thing to pass.
    """
    doc = _open(file_path)
    try:
        if isinstance(pages, str):
            wanted = _parse_pages(doc, pages)
        elif pages:
            wanted = [p - 1 for p in pages]
        else:
            wanted = list(range(doc.page_count))

        shift = _detect_shift(doc, file_path)
        out = []
        for index in wanted:
            if not 0 <= index < doc.page_count:
                continue
            page = doc[index]
            text = page.get_text()
            ocr_used = False
            if not text.strip():
                text = _ocr_page(page)
                ocr_used = True
            else:
                text = _shift_text(text, shift)
            out.append(
                {
                    "source_page": index + 1,
                    "text": text,
                    "ocr_used": ocr_used,
                    "char_count": len(text),
                }
            )
        return {
            "file": file_path,
            "page_count": doc.page_count,
            "encoding_repaired": bool(shift),
            "encoding_shift": shift,
            "encoding_note": (
                f"This PDF embeds fonts with no usable ToUnicode map; glyph codes were "
                f"offset back by {shift} to recover readable text. Check any value that "
                f"looks wrong against the drawing."
                if shift
                else None
            ),
            "pages": out,
        }
    finally:
        doc.close()


def _union_bbox(words: list[tuple]) -> list[float]:
    """Union bounding box of a group of words, as [x0, y0, x1, y1] in PDF points."""
    return [
        round(min(w[0] for w in words), 2),
        round(min(w[1] for w in words), 2),
        round(max(w[2] for w in words), 2),
        round(max(w[3] for w in words), 2),
    ]


def _rows_from_words(
    page: fitz.Page, region: list[float] | None = None, shift: int = 0
) -> list[dict[str, Any]]:
    """Cluster positioned words into rows of cells.

    This is the core of schedule extraction: CAD sheets place every label as a
    free-floating text run, so rows have to be recovered geometrically.

    Each row and cell keeps its bounding box so a reviewer can be shown the exact
    spot on the real page a value was read from (NFR-3).
    """
    words = page.get_text("words")  # (x0, y0, x1, y1, word, block, line, word_no)
    if shift:
        words = [(*w[:4], _shift_text(w[4], shift), *w[5:]) for w in words]
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
                "bbox": _union_bbox(line),
                "cells": [" ".join(w[4] for w in cell) for cell in cells],
                "cell_boxes": [_union_bbox(cell) for cell in cells],
                "text": " | ".join(" ".join(w[4] for w in cell) for cell in cells),
            }
        )
    return rows


def extract_tables(
    file_path: str,
    page_range: str | None = None,
    region: list[float] | None = None,
    max_pages: int = MAX_TABLE_PAGES,
) -> dict[str, Any]:
    """Rows of cells clustered from positioned words, bounded per call.

    Ask for the pages you need. Reading a whole bid set in one call costs more
    context than the estimating does - use search_pdf to find the schedule sheet
    first, then read that page.
    """
    doc = _open(file_path)
    try:
        shift = _detect_shift(doc, file_path)
        requested = _parse_pages(doc, page_range)
        reading, deferred = requested[:max_pages], requested[max_pages:]
        out = []
        for index in reading:
            page = doc[index]
            rows = _rows_from_words(page, region, shift)
            # A dropped row is a missing opening in a quote, so a page that had to
            # be cut says so and says how much - never just a shorter list.
            total_rows = len(rows)
            truncated = total_rows > MAX_ROWS_PER_PAGE
            if truncated:
                rows = rows[:MAX_ROWS_PER_PAGE]
            if rows:
                out.append(
                    {
                        "source_page": index + 1,
                        "page_size": {
                            "width": round(page.rect.width, 2),
                            "height": round(page.rect.height, 2),
                        },
                        "row_count": len(rows),
                        "row_count_on_page": total_rows,
                        "rows_truncated": truncated,
                        "rows_note": (
                            f"Only the first {MAX_ROWS_PER_PAGE} of {total_rows} rows are "
                            f"here. Narrow with `region` to read the rest of this sheet."
                            if truncated
                            else None
                        ),
                        "rows": rows,
                    }
                )
        return {
            "file": file_path,
            "method": "word-position clustering",
            "encoding_repaired": bool(shift),
            "encoding_shift": shift,
            "pages_read": [i + 1 for i in reading],
            "pages_deferred": [i + 1 for i in deferred],
            "note": (
                f"{len(deferred)} of the {len(requested)} requested pages were not read, "
                f"to keep one call from spending the context the estimating needs. "
                f"Ask for them explicitly, e.g. page_range="
                f"'{deferred[0] + 1}-{deferred[-1] + 1}'."
                if deferred
                else None
            ),
            "pages": out,
        }
    finally:
        doc.close()


def find_sheets(file_path: str, queries: list[str] | None = None) -> dict[str, Any]:
    """A page map: which sheets mention which terms, and how often.

    The first question of every take-off is "which sheets matter?", and answering
    it with one `search_pdf` per term costs a turn and a page of context each -
    six searches on a one-page probe, for an answer that fits on a line.

    This returns counts rather than surrounding text: enough to choose the two or
    three sheets worth reading properly, and not enough to be tempted to read the
    set from here.
    """
    terms = [q for q in (queries or DEFAULT_SHEET_TERMS) if q and q.strip()]
    doc = _open(file_path)
    try:
        shift = _detect_shift(doc, file_path)
        pages: list[dict[str, Any]] = []
        totals: dict[str, int] = {t: 0 for t in terms}

        for index in range(doc.page_count):
            text = _shift_text(doc[index].get_text(), shift).lower()
            hits = {t: text.count(t.lower()) for t in terms}
            hits = {t: n for t, n in hits.items() if n}
            if not hits:
                continue
            for term, count in hits.items():
                totals[term] += count
            pages.append(
                {
                    "source_page": index + 1,
                    "terms": dict(sorted(hits.items(), key=lambda kv: -kv[1])),
                    "score": sum(hits.values()),
                }
            )

        pages.sort(key=lambda p: -p["score"])
        return {
            "file": file_path,
            "page_count": doc.page_count,
            "encoding_repaired": bool(shift),
            "queried": terms,
            "not_found": sorted(t for t, n in totals.items() if not n),
            "pages": pages,
            "note": (
                "Ranked by how many of the queried terms each sheet carries. Read the "
                "top sheets with extract_tables; do not read them all."
            ),
        }
    finally:
        doc.close()


def get_page_size(file_path: str, page_number: int) -> dict[str, Any]:
    """Page dimensions in PDF points - the frame every bbox is measured against."""
    doc = _open(file_path)
    try:
        index = page_number - 1
        if not 0 <= index < doc.page_count:
            raise ValueError(f"page {page_number} out of range (1-{doc.page_count})")
        rect = doc[index].rect
        return {
            "file": file_path,
            "source_page": page_number,
            "page_count": doc.page_count,
            "width": round(rect.width, 2),
            "height": round(rect.height, 2),
            "units": "PDF points",
        }
    finally:
        doc.close()


def get_page_image(
    file_path: str,
    page_number: int,
    dpi: int = 200,
    out_dir: str | None = None,
) -> dict[str, Any]:
    doc = _open(file_path)
    try:
        index = page_number - 1
        if not 0 <= index < doc.page_count:
            raise ValueError(f"page {page_number} out of range (1-{doc.page_count})")
        target = Path(out_dir) if out_dir else Path(file_path).parent
        target.mkdir(parents=True, exist_ok=True)
        output = target / f"{Path(file_path).stem}_p{page_number}_{dpi}dpi.png"
        doc[index].get_pixmap(dpi=dpi).save(output)
        return {
            "source_page": page_number,
            "image_path": str(output),
            "dpi": dpi,
            "file": file_path,
        }
    finally:
        doc.close()


def search_pdf(
    file_path: str, query: str, context_chars: int = 160, max_hits: int = 40
) -> dict[str, Any]:
    """Where a phrase appears, with enough context to tell hits apart.

    This is the cheap way to find the sheet you want before reading it. The
    context window is deliberately small - a search that returns the page is
    doing its job; extract_tables reads it.
    """
    doc = _open(file_path)
    try:
        needle = query.lower()
        half = max(context_chars // 2, 40)
        # Without the repair a search for "DOOR SCHEDULE" finds nothing on a set
        # whose glyph codes are offset, and reports it as absent rather than as
        # unreadable - the worst possible answer.
        shift = _detect_shift(doc, file_path)
        hits: list[dict[str, Any]] = []
        for index in range(doc.page_count):
            text = _shift_text(doc[index].get_text(), shift)
            lowered = text.lower()
            start = lowered.find(needle)
            while start != -1 and len(hits) < max_hits:
                left = max(0, start - half)
                hits.append(
                    {
                        "source_page": index + 1,
                        "offset": start,
                        "context": text[left : start + len(query) + half],
                    }
                )
                start = lowered.find(needle, start + 1)
            if len(hits) >= MAX_HITS:
                break
        return {"file": file_path, "query": query, "hit_count": len(hits), "hits": hits}
    finally:
        doc.close()


HANDLERS = {
    "find_sheets": find_sheets,
    "extract_text": extract_text,
    "extract_tables": extract_tables,
    "get_page_image": get_page_image,
    "get_page_size": get_page_size,
    "search_pdf": search_pdf,
}


if __name__ == "__main__":
    serve("pdf-tools", TOOLS, HANDLERS)
