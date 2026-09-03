"""B-11: worker sheetmap pre-pass writes ranked pages and is a no-op on matching SHA."""
from __future__ import annotations

from pathlib import Path

import fitz

from apps.worker import prompts
from cbc.services import sheetmap


def _tiny_pdf(path: Path, text: str = "DOOR SCHEDULE") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    try:
        page = doc.new_page(width=200, height=200)
        page.insert_text((20, 80), text, fontsize=12)
        doc.save(path)
    finally:
        doc.close()
    return path


def test_build_sheetmap_ranks_pages_and_skips_unchanged(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sheetmap, "PROJECTS", tmp_path / "projects")
    slug = "sheetmap_demo"
    pdf = _tiny_pdf(tmp_path / "projects" / slug / "uploads" / "raw" / "set.pdf")
    first = sheetmap.build_sheetmap(slug)
    target = sheetmap.sheetmap_path(slug)
    assert target.is_file()
    assert first["files"]
    pages = first["files"][0]["pages"]
    assert pages
    assert any(p.get("markers") or "door" in str(p.get("terms")).lower() for p in pages)
    generated = first["generated_at"]
    second = sheetmap.build_sheetmap(slug)
    assert second["generated_at"] == generated
    assert pdf.exists()
    forced = sheetmap.build_sheetmap(slug, force=True)
    assert forced["generated_at"] != generated


def test_extract_prompt_names_the_sheetmap() -> None:
    text = prompts.build(
        {"type": "extract_bid_set", "payload": {}},
        {"slug": "demo", "code": "CBC-1"},
    )
    assert "_sheetmap.json" in text
    assert "find_sheets" in text
