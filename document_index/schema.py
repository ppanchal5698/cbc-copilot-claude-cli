"""Step B — schema discovery via LLM (once per document)."""
from __future__ import annotations

import json
import re

from cbc_core.llm import LLMClient, load_prompt
from document_index.models import FieldSchema, PageExtract, SchemaConfig


def _sample_pages(pages: list[PageExtract], count: int = 18) -> list[PageExtract]:
    if len(pages) <= count:
        return pages
    indices: set[int] = set()
    for fraction in (0, 0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0):
        indices.add(min(len(pages) - 1, int(fraction * (len(pages) - 1))))
    while len(indices) < count:
        step = max(1, len(pages) // count)
        for i in range(0, len(pages), step):
            indices.add(i)
            if len(indices) >= count:
                break
    chosen = sorted(indices)[:count]
    return [pages[i] for i in chosen]


def _fallback_schema(pages: list[PageExtract]) -> SchemaConfig:
    """Deterministic schema when LLM is unavailable (tests / offline)."""
    sample = "\n".join(p.text[:500] for p in pages[:5])
    has_price = bool(re.search(r"\$\s*\d", sample))
    return SchemaConfig(
        anchor_pattern=r"^[A-Z0-9][A-Z0-9\-./]{2,}",
        price_or_key_value_regex=r"\$\s*[\d,]+(?:\.\d{2})?" if has_price else r"^[A-Z0-9][A-Z0-9\-./]{2,}",
        code_regex=r"[A-Z0-9][A-Z0-9\-./]{2,}",
        field_schema=[
            FieldSchema(name="code", type="string"),
            FieldSchema(name="description", type="string"),
            FieldSchema(name="price", type="number"),
        ],
        spans_multiple_pages=True,
        notes="fallback heuristic schema",
    )


def discover_schema(
    pages: list[PageExtract],
    llm: LLMClient | None,
    *,
    document_id: str,
) -> SchemaConfig:
    if not pages:
        raise ValueError("cannot discover schema from zero pages")

    if llm is None:
        return _fallback_schema(pages)

    samples = _sample_pages(pages)
    sample_text = "\n\n".join(
        f"--- Page {p.page_number} {'(visual)' if p.visual_page else ''} ---\n{p.text[:3000]}"
        for p in samples
    )
    system = load_prompt("schema_discovery.txt")
    response = llm.complete_json(
        system=system,
        user=sample_text,
        document_id=document_id,
        prompt_version="schema_discovery.txt",
    )
    raw = response.data
    fields = [
        FieldSchema(**item) if isinstance(item, dict) else FieldSchema(name=str(item))
        for item in raw.get("field_schema") or []
    ]
    return SchemaConfig(
        anchor_pattern=str(raw.get("anchor_pattern") or "^[A-Z0-9]"),
        price_or_key_value_regex=str(raw.get("price_or_key_value_regex") or r"\$\s*[\d,]+"),
        code_regex=str(raw.get("code_regex") or r"[A-Z0-9\-./]{2,}"),
        field_schema=fields or _fallback_schema(pages).field_schema,
        spans_multiple_pages=bool(raw.get("spans_multiple_pages", True)),
        notes=raw.get("notes"),
    )


def schema_to_prompt_json(schema: SchemaConfig) -> str:
    return json.dumps(schema.model_dump(), indent=2)
