"""Anchor-based section splitting using discovered schema."""
from __future__ import annotations

import re
from dataclasses import dataclass

from cbc.documents.models import PageExtract, SchemaConfig


@dataclass
class SectionChunk:
    page_range: list[int]
    section_title: str
    raw_text: str


def split_into_sections(pages: list[PageExtract], schema: SchemaConfig) -> list[SectionChunk]:
    if not pages:
        return []

    try:
        anchor = re.compile(schema.anchor_pattern, re.MULTILINE | re.IGNORECASE)
    except re.error:
        anchor = re.compile(r"^[A-Z0-9]", re.MULTILINE)

    if schema.spans_multiple_pages:
        full_text = "\n\n".join(f"[p{p.page_number}]\n{p.text}" for p in pages)
        return _split_full_text(full_text, pages, anchor)

    chunks: list[SectionChunk] = []
    for page in pages:
        chunks.extend(_split_page(page, anchor))
    return chunks or [_whole_document(pages)]


def _whole_document(pages: list[PageExtract]) -> SectionChunk:
    return SectionChunk(
        page_range=[pages[0].page_number, pages[-1].page_number],
        section_title="Document",
        raw_text="\n\n".join(p.text for p in pages),
    )


def _split_page(page: PageExtract, anchor: re.Pattern[str]) -> list[SectionChunk]:
    matches = list(anchor.finditer(page.text))
    if not matches:
        return [
            SectionChunk(
                page_range=[page.page_number, page.page_number],
                section_title=f"Page {page.page_number}",
                raw_text=page.text,
            )
        ]

    chunks: list[SectionChunk] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(page.text)
        title = match.group(0).strip()[:80] or f"Section {index + 1}"
        chunks.append(
            SectionChunk(
                page_range=[page.page_number, page.page_number],
                section_title=title,
                raw_text=page.text[start:end].strip(),
            )
        )
    return chunks


def _split_full_text(
    full_text: str,
    pages: list[PageExtract],
    anchor: re.Pattern[str],
) -> list[SectionChunk]:
    matches = list(anchor.finditer(full_text))
    if not matches:
        return [_whole_document(pages)]

    page_starts = {p.page_number: p.text for p in pages}
    chunks: list[SectionChunk] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(full_text)
        section_text = full_text[start:end].strip()
        title = match.group(0).strip()[:80] or f"Section {index + 1}"
        page_range = _page_range_for_text(section_text, pages)
        chunks.append(
            SectionChunk(
                page_range=page_range,
                section_title=title,
                raw_text=section_text,
            )
        )
    return chunks


def _page_range_for_text(text: str, pages: list[PageExtract]) -> list[int]:
    referenced: list[int] = []
    for page in pages:
        marker = f"[p{page.page_number}]"
        if marker in text or page.text[:200] in text:
            referenced.append(page.page_number)
    if referenced:
        return [min(referenced), max(referenced)]
    return [pages[0].page_number, pages[-1].page_number]
