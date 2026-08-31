"""Tests for versioning and no-overwrite guarantees."""
from __future__ import annotations

from pathlib import Path

import pytest

from cbc.documents import storage
from cbc.documents.versioning import (
    get_current_version,
    list_versions,
    promote_current_version,
    register_version,
    registry_path,
)


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCUMENT_INDEX_ROOT", str(tmp_path))
    registry = tmp_path / "registry.json"
    if registry.exists():
        registry.unlink()
    yield tmp_path


def test_two_uploads_create_two_folders(isolated_registry: Path):
    first_id = storage.allocate_document_id()
    second_id = storage.allocate_document_id()
    assert first_id != second_id

    folder1 = storage.document_dir("hager", "multiplier_sheet", "2026-01-01", first_id)
    folder2 = storage.document_dir("hager", "multiplier_sheet", "2026-01-01", second_id)

    register_version(
        document_id=first_id,
        client_id="hager",
        document_type="multiplier_sheet",
        effective_date="2026-01-01",
        folder=folder1,
        source_path="pricebooks/a.pdf",
    )
    register_version(
        document_id=second_id,
        client_id="hager",
        document_type="multiplier_sheet",
        effective_date="2026-01-01",
        folder=folder2,
        source_path="pricebooks/b.pdf",
    )

    folder1.mkdir(parents=True)
    folder2.mkdir(parents=True)
    (folder1 / "manifest.json").write_text("{}", encoding="utf-8")
    (folder2 / "manifest.json").write_text("{}", encoding="utf-8")

    versions = list_versions("hager", "multiplier_sheet")
    ids = {v["document_id"] for v in versions}
    assert first_id in ids
    assert second_id in ids
    assert folder1 != folder2


def test_current_version_not_set_with_review_needed(isolated_registry: Path):
    doc_id = storage.allocate_document_id()
    folder = storage.document_dir("hager", "price_book", "2026-02-01", doc_id)
    register_version(
        document_id=doc_id,
        client_id="hager",
        document_type="price_book",
        effective_date="2026-02-01",
        folder=folder,
        source_path="pricebooks/x.pdf",
    )
    promoted = promote_current_version(
        doc_id, "hager", "price_book", review_count=3
    )
    assert promoted is False
    assert get_current_version("hager", "price_book") is None


def test_current_version_set_when_clean(isolated_registry: Path):
    doc_id = storage.allocate_document_id()
    folder = storage.document_dir("hager", "price_book", "2026-02-01", doc_id)
    register_version(
        document_id=doc_id,
        client_id="hager",
        document_type="price_book",
        effective_date="2026-02-01",
        folder=folder,
        source_path="pricebooks/x.pdf",
    )
    assert promote_current_version(doc_id, "hager", "price_book", review_count=0)
    assert get_current_version("hager", "price_book") == doc_id


def test_registry_file_created(isolated_registry: Path):
    doc_id = storage.allocate_document_id()
    folder = storage.document_dir("bobrick", "price_book", "2026-03-01", doc_id)
    register_version(
        document_id=doc_id,
        client_id="bobrick",
        document_type="price_book",
        effective_date="2026-03-01",
        folder=folder,
        source_path="pricebooks/b.pdf",
    )
    assert registry_path().exists()
