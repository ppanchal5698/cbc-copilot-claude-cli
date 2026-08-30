"""PDF services for the review screen.

The estimator checks an extracted value against the real drawing, so the API
serves real page renders and the raw file. Bboxes come from extraction and are
measured in PDF points against `page_size`; the viewer scales them itself.

The page operations come from `cbc_core.pdfpages`, which the pdf-tools MCP server
also uses - so a bbox the estimator is shown is measured against exactly the frame
a run recorded it in. This module adds the render cache on top.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from api.config import settings
from cbc_core import pdfpages

RENDER_CACHE = pdfpages.RENDER_CACHE  # one cache, shared with the MCP server
MAX_DPI = 300
MIN_DPI = 36

page_count = pdfpages.page_count
find_text = pdfpages.find_text


def page_size(path: Path, page_number: int) -> dict[str, Any]:
    return pdfpages.page_size(path, page_number)


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

    produced = Path(
        pdfpages.page_image(path, page_number=page_number, dpi=dpi, out_dir=RENDER_CACHE)[
            "image_path"
        ]
    )
    produced.replace(cached)
    return cached
