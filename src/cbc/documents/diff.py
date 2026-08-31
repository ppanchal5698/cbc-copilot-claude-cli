"""Diff report between document versions."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cbc.documents.models import DiffEntry, DiffReport
from cbc.documents import storage


def _load_index(folder: Path) -> list[dict[str, Any]]:
    path = folder / "index.json"
    if not path.exists():
        return []
    return storage.read_json(path)


def _entity_prices(folder: Path) -> dict[str, float | None]:
    """Map entity code → price from extracted records."""
    content_path = folder / "content.db"
    if not content_path.exists():
        return {}

    from cbc.documents import db as content_db

    connection = content_db.connect(content_path, readonly=True)
    try:
        rows = connection.execute(
            "SELECT extracted_records FROM sections"
        ).fetchall()
    finally:
        connection.close()

    prices: dict[str, float | None] = {}
    for row in rows:
        records = json.loads(row["extracted_records"])
        for record in records:
            if not isinstance(record, dict):
                continue
            code = str(record.get("code") or record.get("part") or "").strip().upper()
            if not code:
                continue
            price = record.get("price")
            if isinstance(price, (int, float)):
                prices[code] = float(price)
            elif code not in prices:
                prices[code] = None
    return prices


def _entities_from_index(entries: list[dict[str, Any]]) -> set[str]:
    found: set[str] = set()
    for entry in entries:
        for entity in entry.get("entities_present") or []:
            found.add(str(entity).strip().upper())
    return found


def generate_diff_report(
    old_folder: Path,
    new_folder: Path,
    *,
    from_document_id: str,
    to_document_id: str,
    client_id: str,
    document_type: str,
) -> DiffReport:
    old_index = _load_index(old_folder)
    new_index = _load_index(new_folder)
    old_entities = _entities_from_index(old_index)
    new_entities = _entities_from_index(new_index)

    added = sorted(new_entities - old_entities)
    removed = sorted(old_entities - new_entities)

    old_prices = _entity_prices(old_folder)
    new_prices = _entity_prices(new_folder)
    changed: list[DiffEntry] = []

    for entity in sorted(old_entities & new_entities):
        old_price = old_prices.get(entity)
        new_price = new_prices.get(entity)
        if old_price != new_price:
            changed.append(
                DiffEntry(
                    entity=entity,
                    change_type="changed",
                    field="price",
                    old_value=old_price,
                    new_value=new_price,
                )
            )

    report = DiffReport(
        from_document_id=from_document_id,
        to_document_id=to_document_id,
        client_id=client_id,
        document_type=document_type,
        added=added,
        removed=removed,
        changed=changed,
        generated_at=storage.now_iso(),
    )
    storage.write_json(new_folder / "diff_report.json", report.model_dump())
    return report
