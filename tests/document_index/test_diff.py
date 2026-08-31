"""Tests for diff report generation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cbc.documents.diff import generate_diff_report
from cbc.documents import db as content_db


@pytest.fixture
def version_pair(tmp_path):
    old_id = "old-version"
    new_id = "new-version"
    old_folder = tmp_path / "old"
    new_folder = tmp_path / "new"
    old_folder.mkdir()
    new_folder.mkdir()

    old_index = [
        {
            "page_range": [1, 1],
            "section_title": "A",
            "description": "section A",
            "tags": [],
            "entities_present": ["ABC-100", "XYZ-200"],
        }
    ]
    new_index = [
        {
            "page_range": [1, 1],
            "section_title": "A",
            "description": "section A updated",
            "tags": [],
            "entities_present": ["ABC-100", "NEW-300"],
        }
    ]
    (old_folder / "index.json").write_text(json.dumps(old_index), encoding="utf-8")
    (new_folder / "index.json").write_text(json.dumps(new_index), encoding="utf-8")

    def write_content(folder: Path, records: list[dict]) -> None:
        connection = content_db.initialise(folder / "content.db")
        connection.execute(
            "INSERT INTO sections (page_start, page_end, section_title, raw_text, extracted_records, entities_present) "
            "VALUES (1, 1, 'A', 'text', ?, ?)",
            [json.dumps(records), json.dumps([r["code"] for r in records])],
        )
        connection.close()

    write_content(old_folder, [{"code": "ABC-100", "price": 10.0}, {"code": "XYZ-200", "price": 5.0}])
    write_content(
        new_folder,
        [{"code": "ABC-100", "price": 12.0}, {"code": "NEW-300", "price": 8.0}],
    )
    return old_folder, new_folder, old_id, new_id


def test_diff_detects_added_removed_changed(version_pair):
    old_folder, new_folder, old_id, new_id = version_pair
    report = generate_diff_report(
        old_folder,
        new_folder,
        from_document_id=old_id,
        to_document_id=new_id,
        client_id="hager",
        document_type="multiplier_sheet",
    )
    assert "NEW-300" in report.added
    assert "XYZ-200" in report.removed
    changed_entities = [entry.entity for entry in report.changed]
    assert "ABC-100" in changed_entities
    assert (new_folder / "diff_report.json").exists()
