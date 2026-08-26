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


def extract_text(file_path: str, pages: list[int] | None = None) -> dict[str, Any]:
    doc = _open(file_path)
    try:
        wanted = [p - 1 for p in pages] if pages else list(range(doc.page_count))
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
            out.append(
                {
                    "source_page": index + 1,
                    "text": text,
                    "ocr_used": ocr_used,
                    "char_count": len(text),
                }
            )
        return {"file": file_path, "page_count": doc.page_count, "pages": out}
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


def _rows_from_words(page: fitz.Page, region: list[float] | None = None) -> list[dict[str, Any]]:
    """Cluster positioned words into rows of cells.

    This is the core of schedule extraction: CAD sheets place every label as a
    free-floating text run, so rows have to be recovered geometrically.

    Each row and cell keeps its bounding box so a reviewer can be shown the exact
    spot on the real page a value was read from (NFR-3).
    """
    words = page.get_text("words")  # (x0, y0, x1, y1, word, block, line, word_no)
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
) -> dict[str, Any]:
    doc = _open(file_path)
    try:
        out = []
        for index in _parse_pages(doc, page_range):
            page = doc[index]
            rows = _rows_from_words(page, region)
            if rows:
                out.append(
                    {
                        "source_page": index + 1,
                        "page_size": {
                            "width": round(page.rect.width, 2),
                            "height": round(page.rect.height, 2),
                        },
                        "row_count": len(rows),
                        "rows": rows,
                    }
                )
        return {"file": file_path, "method": "word-position clustering", "pages": out}
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


def search_pdf(file_path: str, query: str, context_chars: int = 500) -> dict[str, Any]:
    doc = _open(file_path)
    try:
        needle = query.lower()
        half = max(context_chars // 2, 40)
        hits: list[dict[str, Any]] = []
        for index in range(doc.page_count):
            text = doc[index].get_text()
            lowered = text.lower()
            start = lowered.find(needle)
            while start != -1 and len(hits) < MAX_HITS:
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
    "extract_text": extract_text,
    "extract_tables": extract_tables,
    "get_page_image": get_page_image,
    "get_page_size": get_page_size,
    "search_pdf": search_pdf,
}


if __name__ == "__main__":
    serve("pdf-tools", TOOLS, HANDLERS)
