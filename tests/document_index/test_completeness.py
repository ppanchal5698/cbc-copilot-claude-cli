"""Tests for completeness reconciliation logic."""
from __future__ import annotations

from cbc.documents.completeness import count_regex_matches, reconcile_section, split_text_halves
from cbc.documents.models import SchemaConfig, SectionExtractionResult


def _schema() -> SchemaConfig:
    return SchemaConfig(
        anchor_pattern=r"^[A-Z]",
        price_or_key_value_regex=r"\$\d+",
        code_regex=r"[A-Z0-9]+",
        field_schema=[],
    )


def test_count_regex_matches():
    text = "A $10\nB $20\nC $30"
    assert count_regex_matches(text, r"\$\d+") == 3


def test_split_text_halves():
    text = "line1\nline2\nline3\nline4"
    parts = split_text_halves(text, 2)
    assert len(parts) >= 2


def test_reconcile_accepts_matching_counts():
    schema = _schema()
    raw = "ITEM $10\nITEM $20"

    def extract_fn(text, page_range, title):
        return SectionExtractionResult(
            page_range=page_range,
            section_title=title,
            description=title,
            extracted_records=[{"code": "ITEM"}, {"code": "ITEM"}],
            expected_key_value_count=2,
            produced_record_count=2,
        )

    result, review = reconcile_section(
        raw_text=raw,
        page_range=[1, 1],
        section_title="Test",
        schema=schema,
        extract_fn=extract_fn,
    )
    assert result is not None
    assert review is None
    assert result.produced_record_count == 2


def test_reconcile_emits_review_after_retries():
    schema = _schema()
    raw = "ITEM $10\nITEM $20\nITEM $30"
    calls = {"n": 0}

    def extract_fn(text, page_range, title):
        calls["n"] += 1
        expected = count_regex_matches(text, schema.price_or_key_value_regex)
        # Always under-produce vs regex count
        produced = max(0, expected - 1) if expected else 1
        return SectionExtractionResult(
            page_range=page_range,
            section_title=title,
            description=title,
            extracted_records=[{"code": "ITEM"}] * produced,
            expected_key_value_count=expected,
            produced_record_count=produced,
        )

    result, review = reconcile_section(
        raw_text=raw,
        page_range=[1, 1],
        section_title="Mismatch",
        schema=schema,
        extract_fn=extract_fn,
        max_retries=2,
    )
    assert result is not None
    assert review is not None
    assert review.expected_key_value_count != review.produced_record_count
    assert review.attempts == 2
    assert calls["n"] >= 2
