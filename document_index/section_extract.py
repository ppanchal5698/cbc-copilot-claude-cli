"""Step C — per-section LLM extraction."""
from __future__ import annotations

import json
import re

from cbc_core.llm import LLMClient
from document_index.templates import load_prompt, render_prompt
from document_index.models import SchemaConfig, SectionExtractionResult
from document_index.schema import schema_to_prompt_json


def extract_section_records(
    raw_text: str,
    page_range: list[int],
    section_title: str,
    schema: SchemaConfig,
    llm: LLMClient | None,
    *,
    document_id: str,
) -> SectionExtractionResult:
    if llm is None:
        return _heuristic_extract(raw_text, page_range, section_title, schema)

    template = load_prompt("section_extraction.txt")
    user = render_prompt(
        template,
        schema_config=schema_to_prompt_json(schema),
        page_range=str(page_range),
        raw_text=raw_text[:12000],
    )
    response = llm.complete_json(
        system="Extract structured records from the section text. Return JSON only.",
        user=user,
        document_id=document_id,
        section_id=section_title[:40],
        prompt_version="section_extraction.txt",
    )
    raw = response.data
    records = raw.get("extracted_records") or []
    entities = raw.get("entities_present") or _entities_from_records(records, schema)
    return SectionExtractionResult(
        page_range=raw.get("page_range") or page_range,
        section_title=str(raw.get("section_title") or section_title),
        description=str(raw.get("description") or section_title),
        tags=list(raw.get("tags") or []),
        entities_present=[str(e) for e in entities],
        extracted_records=records if isinstance(records, list) else [],
        expected_key_value_count=int(raw.get("expected_key_value_count") or 0),
        produced_record_count=int(raw.get("produced_record_count") or len(records)),
    )


def _heuristic_extract(
    raw_text: str,
    page_range: list[int],
    section_title: str,
    schema: SchemaConfig,
) -> SectionExtractionResult:
    records: list[dict] = []
    entities: list[str] = []
    try:
        code_re = re.compile(schema.code_regex)
    except re.error:
        code_re = re.compile(r"[A-Z0-9\-./]{2,}")

    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        codes = code_re.findall(line)
        if not codes:
            continue
        code = codes[0]
        entities.append(code)
        price_match = re.search(r"\$\s*([\d,]+(?:\.\d{2})?)", line)
        price = float(price_match.group(1).replace(",", "")) if price_match else None
        records.append({"code": code, "description": line, "price": price})

    return SectionExtractionResult(
        page_range=page_range,
        section_title=section_title,
        description=section_title,
        tags=[],
        entities_present=sorted(set(entities)),
        extracted_records=records,
        expected_key_value_count=len(records),
        produced_record_count=len(records),
    )


def _entities_from_records(records: list, schema: SchemaConfig) -> list[str]:
    entities: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        for field in schema.field_schema:
            if field.name in ("code", "part", "mark") and record.get(field.name):
                entities.append(str(record[field.name]))
        if record.get("code"):
            entities.append(str(record["code"]))
    return sorted(set(entities))
