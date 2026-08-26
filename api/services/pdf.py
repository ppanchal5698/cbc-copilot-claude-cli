"""PDF services for the review screen.

The estimator checks an extracted value against the real drawing, so the API
serves real page renders and the raw file. Bboxes come from extraction and are
measured in PDF points against `page_size`; the viewer scales them itself.

Reuses the pdf-tools MCP server rather than opening PyMuPDF a second way.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

from api.config import settings

sys.path.insert(0, str(settings.repo_root / "mcp-servers"))

from _runtime import load_server  # noqa: E402

pdf_tools = load_server("pdf-tools")

RENDER_CACHE = settings.repo_root / ".cache" / "pdf-pages"
MAX_DPI = 300
MIN_DPI = 36


def page_count(path: Path) -> int:
    import fitz

    doc = fitz.open(path)
    try:
        return doc.page_count
    finally:
        doc.close()


def page_size(path: Path, page_number: int) -> dict[str, Any]:
    return pdf_tools.get_page_size(str(path), page_number)


def render_page(path: Path, page_number: int, dpi: int = 110) -> Path:
    """Render one page to PNG, cached by file identity + page + dpi.

    ponytail: cache key is path + mtime + size, not a content hash - hashing a
    15 MB drawing on every page view costs more than it saves. Raw uploads are
    immutable, so mtime is a sound identity here.
    """
    dpi = max(MIN_DPI, min(int(dpi), MAX_DPI))
    stat = path.stat()
    key = hashlib.sha256(
        f"{path.resolve()}|{stat.st_mtime_ns}|{stat.st_size}|{page_number}|{dpi}".encode()
    ).hexdigest()[:24]

    RENDER_CACHE.mkdir(parents=True, exist_ok=True)
    cached = RENDER_CACHE / f"{key}.png"
    if cached.exists():
        return cached

    result = pdf_tools.get_page_image(
        str(path), page_number=page_number, dpi=dpi, out_dir=str(RENDER_CACHE)
    )
    if "error" in result:
        raise ValueError(result["error"])

    produced = Path(result["image_path"])
    produced.replace(cached)
    return cached


def find_text(path: Path, page_number: int, needle: str) -> list[dict[str, Any]]:
    """Locate a string on a page and return its bboxes.

    Fallback for a line whose stored bbox is missing - an older extraction, or a
    value the estimator typed by hand and wants to point at.
    """
    import fitz

    doc = fitz.open(path)
    try:
        index = page_number - 1
        if not 0 <= index < doc.page_count:
            return []
        page = doc[index]
        return [
            {
                "bbox": [round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)],
                "pageSize": {"width": round(page.rect.width, 2), "height": round(page.rect.height, 2)},
            }
            for r in page.search_for(needle)[:20]
        ]
    finally:
        doc.close()
