"""Reading a page's geometry and rendering it to an image.

The estimator checks an extracted value against the real drawing, so the API
serves real page renders; the pdf-tools MCP server offers the same two operations
to a run. Both used to have their own copy - or worse, the API exec-ed the
server's module in-process through a custom loader to borrow them.

Bboxes are measured in PDF points against `page_size`, and the viewer scales them
itself, so these two have to agree exactly. Here they are the same code.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parents[1]

# Rendered pages are derived data: cheap to recreate, and not something to leave
# beside the drawings they came from. Shared with api/services/pdf.py so there is
# one cache rather than two.
RENDER_CACHE = ROOT / ".cache" / "pdf-pages"
PRICEBOOKS = ROOT / "pricebooks"
REFERENCE_LIBRARY = ROOT / "reference-library"


def _open(file_path: str | Path) -> fitz.Document:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")
    return fitz.open(path)


def page_count(file_path: str | Path) -> int:
    doc = _open(file_path)
    try:
        return doc.page_count
    finally:
        doc.close()


def page_size(file_path: str | Path, page_number: int) -> dict[str, Any]:
    """Page dimensions in PDF points - the frame every bbox is measured against."""
    doc = _open(file_path)
    try:
        index = page_number - 1
        if not 0 <= index < doc.page_count:
            raise ValueError(f"page {page_number} out of range (1-{doc.page_count})")
        rect = doc[index].rect
        return {
            "file": str(file_path),
            "source_page": page_number,
            "page_count": doc.page_count,
            "width": round(rect.width, 2),
            "height": round(rect.height, 2),
            "units": "PDF points",
        }
    finally:
        doc.close()


def _writable_target(file_path: Path, out_dir: str | Path | None) -> Path:
    """Where a rendered page may be written.

    Defaulting to the source PDF's own directory was wrong in two ways that only
    show up in a real run. Rendering a page of a bid set dropped
    `1_Architectural_p12_200dpi.png` into `projects/{slug}/uploads/raw/`, where
    `.claude/rules/file-safety.md` says the uploads are immutable and extraction
    output belongs in `uploads/processed/` or `extracted/`. Rendering a page of a
    price book would try to write into `pricebooks/`, which is read-only during a
    run and mounted `:ro` on the worker.

    Neither was caught by the PreToolUse guard, because this write happens inside
    PyMuPDF rather than through Write or Bash - so the check lives here, next to
    the write it governs.
    """
    target = Path(out_dir).resolve() if out_dir else RENDER_CACHE
    for protected in (PRICEBOOKS, REFERENCE_LIBRARY):
        if target == protected or protected in target.parents:
            raise ValueError(
                f"refusing to write a rendered page into {protected.name}/ - it is "
                "read-only reference data (.claude/rules/file-safety.md)"
            )
    if target.name == "raw" and target.parent.name == "uploads":
        raise ValueError(
            "refusing to write a rendered page into uploads/raw/ - raw uploads are "
            "immutable; use uploads/processed/ or leave out_dir unset"
        )
    return target


def page_image(
    file_path: str | Path,
    page_number: int,
    dpi: int = 200,
    out_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Render one page to PNG. Writes to the shared cache unless told otherwise."""
    doc = _open(file_path)
    try:
        index = page_number - 1
        if not 0 <= index < doc.page_count:
            raise ValueError(f"page {page_number} out of range (1-{doc.page_count})")
        target = _writable_target(Path(file_path), out_dir)
        target.mkdir(parents=True, exist_ok=True)
        output = target / f"{Path(file_path).stem}_p{page_number}_{dpi}dpi.png"
        doc[index].get_pixmap(dpi=dpi).save(output)
        return {
            "source_page": page_number,
            "image_path": str(output),
            "dpi": dpi,
            "file": str(file_path),
        }
    finally:
        doc.close()


def find_text(file_path: str | Path, page_number: int, needle: str) -> list[dict[str, Any]]:
    """Locate a string on a page and return its bboxes.

    Fallback for a line whose stored bbox is missing - an older extraction, or a
    value the estimator typed by hand and wants to point at.
    """
    doc = _open(file_path)
    try:
        index = page_number - 1
        if not 0 <= index < doc.page_count:
            return []
        page = doc[index]
        return [
            {
                "bbox": [round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)],
                "pageSize": {
                    "width": round(page.rect.width, 2),
                    "height": round(page.rect.height, 2),
                },
            }
            for r in page.search_for(needle)[:20]
        ]
    finally:
        doc.close()
