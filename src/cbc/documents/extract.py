"""Step A — per-page text extraction with visual-page detection."""
from __future__ import annotations

from pathlib import Path

import fitz

from cbc.core.pdfrows import detect_shift, has_text_layer, ocr_page, shift_text
from cbc.documents.models import PageExtract

# Characters per square point below which a page is treated as mostly visual.
TEXT_DENSITY_THRESHOLD = 0.002
MIN_TEXT_CHARS = 40


def extract_pages(path: Path) -> list[PageExtract]:
    """Extract raw text for every page in a PDF."""
    doc = fitz.open(path)
    try:
        shift = detect_shift(doc, str(path))
        pages: list[PageExtract] = []
        for index in range(doc.page_count):
            page = doc[index]
            page_number = index + 1
            text = page.get_text()
            if shift:
                text = shift_text(text, shift)
            visual = _is_visual_page(page, text)
            if visual and not has_text_layer(page, minimum_chars=MIN_TEXT_CHARS):
                ocr_text = ocr_page(page)
                if ocr_text and not ocr_text.startswith("["):
                    text = ocr_text
                    visual = False
            pages.append(
                PageExtract(
                    page_number=page_number,
                    text=text.strip(),
                    visual_page=visual,
                )
            )
        return pages
    finally:
        doc.close()


def _is_visual_page(page: fitz.Page, text: str) -> bool:
    if len(text.strip()) < MIN_TEXT_CHARS:
        return True
    rect = page.rect
    area = max(rect.width * rect.height, 1.0)
    return len(text.strip()) / area < TEXT_DENSITY_THRESHOLD
