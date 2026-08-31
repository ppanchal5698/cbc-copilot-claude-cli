"""Completeness reconciliation — expected vs produced record counts."""
from __future__ import annotations

import re
from typing import Callable

from cbc.documents.models import ReviewItem, SchemaConfig, SectionExtractionResult


def count_regex_matches(text: str, pattern: str) -> int:
    if not pattern or not text:
        return 0
    try:
        return len(re.findall(pattern, text, flags=re.MULTILINE | re.IGNORECASE))
    except re.error:
        return 0


def split_text_halves(text: str, parts: int) -> list[str]:
    """Split text into roughly equal chunks for retry."""
    if parts <= 1 or not text:
        return [text]
    lines = text.splitlines()
    if len(lines) <= parts:
        return [line for line in lines if line.strip()] or [text]
    chunk_size = max(1, len(lines) // parts)
    chunks: list[str] = []
    for start in range(0, len(lines), chunk_size):
        piece = "\n".join(lines[start : start + chunk_size]).strip()
        if piece:
            chunks.append(piece)
    return chunks or [text]


def reconcile_section(
    *,
    raw_text: str,
    page_range: list[int],
    section_title: str,
    schema: SchemaConfig,
    extract_fn: Callable[[str, list[int], str], SectionExtractionResult],
    max_retries: int = 2,
) -> tuple[SectionExtractionResult | None, ReviewItem | None]:
    """Extract a section; re-split and retry when counts mismatch."""

    def _attempt(text: str, attempt: int) -> SectionExtractionResult:
        result = extract_fn(text, page_range, section_title)
        result.expected_key_value_count = count_regex_matches(text, schema.price_or_key_value_regex)
        result.produced_record_count = len(result.extracted_records)
        return result

    result = _attempt(raw_text, 0)
    if result.expected_key_value_count == result.produced_record_count:
        return result, None

    for attempt in range(1, max_retries + 1):
        chunks = split_text_halves(raw_text, attempt + 1)
        merged_records: list[dict] = []
        merged_entities: list[str] = []
        total_expected = 0
        total_produced = 0
        titles: list[str] = []
        descriptions: list[str] = []
        tags: set[str] = set()

        for chunk in chunks:
            partial = _attempt(chunk, attempt)
            total_expected += partial.expected_key_value_count
            total_produced += partial.produced_record_count
            merged_records.extend(partial.extracted_records)
            merged_entities.extend(partial.entities_present)
            if partial.section_title:
                titles.append(partial.section_title)
            if partial.description:
                descriptions.append(partial.description)
            tags.update(partial.tags)

        if total_expected == total_produced:
            return SectionExtractionResult(
                page_range=page_range,
                section_title=titles[0] if titles else section_title,
                description=" ".join(descriptions)[:500],
                tags=sorted(tags),
                entities_present=sorted(set(merged_entities)),
                extracted_records=merged_records,
                expected_key_value_count=total_expected,
                produced_record_count=total_produced,
            ), None

        result = SectionExtractionResult(
            page_range=page_range,
            section_title=section_title,
            description=result.description,
            tags=result.tags,
            entities_present=merged_entities,
            extracted_records=merged_records,
            expected_key_value_count=total_expected,
            produced_record_count=total_produced,
        )

    review = ReviewItem(
        page_range=page_range,
        section_title=section_title,
        expected_key_value_count=result.expected_key_value_count,
        produced_record_count=result.produced_record_count,
        attempts=max_retries,
        reason=(
            f"expected {result.expected_key_value_count} key/value matches but "
            f"produced {result.produced_record_count} records after {max_retries} retries"
        ),
    )
    return result, review
