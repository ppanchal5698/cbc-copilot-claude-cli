"""Deterministic sheet map written before a take-off prompt is built (B-11).

`find_sheets` is the same work on every extract job. The worker runs it once,
merges schedule-marker pages from `parse_schedule.find_schedule_pages`, and
writes `extracted/_sheetmap.json` so Claude reads the ranked pages instead of
searching the set again.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cbc.core import pdfpages
from cbc.core.paths import repo_root

ROOT = repo_root()
PROJECTS = ROOT / "projects"
SHEETMAP_REL = "extracted/_sheetmap.json"
SHEETMAP_JOB_TYPES = frozenset(
    {
        "extract_bid_set",
        "rerun_extraction",
        "ingest_addendum",
        "run_full_pipeline",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sheetmap_path(slug: str) -> Path:
    return PROJECTS / slug / SHEETMAP_REL


def _load_parse_schedule():
    path = (
        ROOT
        / ".claude"
        / "skills"
        / "extract-door-schedule"
        / "scripts"
        / "parse_schedule.py"
    )
    name = "cbc_parse_schedule"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _find_sheets(file_path: str) -> dict[str, Any]:
    mcp = ROOT / "mcp-servers"
    if str(mcp) not in sys.path:
        sys.path.insert(0, str(mcp))
    from _runtime import load_server

    return load_server("pdf-tools").find_sheets(file_path)


def _merge_pages(ranked: dict[str, Any], markers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_marker = {int(row["source_page"]): list(row.get("markers") or []) for row in markers}
    pages: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in ranked.get("pages") or []:
        source_page = int(row["source_page"])
        seen.add(source_page)
        terms = row.get("terms") or {}
        found = by_marker.get(source_page) or []
        pages.append(
            {
                "source_page": source_page,
                "score": row.get("score") or 0,
                "terms": terms,
                "kind": "schedule" if found else "ranked",
                "why": ", ".join(found) if found else ", ".join(str(t) for t in terms),
                "markers": found,
            }
        )
    for source_page, found in sorted(by_marker.items()):
        if source_page in seen:
            continue
        pages.append(
            {
                "source_page": source_page,
                "score": 0,
                "terms": {},
                "kind": "schedule",
                "why": ", ".join(found),
                "markers": found,
            }
        )
    pages.sort(key=lambda p: (-int(p.get("score") or 0), int(p["source_page"])))
    return pages


def _file_entry(pdf: Path) -> dict[str, Any]:
    path = str(pdf)
    ranked = _find_sheets(path)
    parse = _load_parse_schedule()
    markers = parse.find_schedule_pages(path)
    rel = f"uploads/raw/{pdf.name}"
    return {
        "path": rel,
        "file_sha": pdfpages.content_sha256(pdf),
        "page_count": ranked.get("page_count") or 0,
        "pages": _merge_pages(ranked, markers),
    }


def _unchanged(existing: dict[str, Any], files: list[Path]) -> bool:
    recorded = {
        row.get("path"): row.get("file_sha")
        for row in (existing.get("files") or [])
        if isinstance(row, dict)
    }
    if len(recorded) != len(files):
        return False
    for pdf in files:
        rel = f"uploads/raw/{pdf.name}"
        if recorded.get(rel) != pdfpages.content_sha256(pdf):
            return False
    return True


def build_sheetmap(slug: str, *, force: bool = False) -> dict[str, Any]:
    """Write `extracted/_sheetmap.json` for every PDF under uploads/raw/.

    Skip the rewrite when every file SHA already matches, unless `force`.
    Does not write `door_schedule.json`.
    """
    project = PROJECTS / slug
    raw = project / "uploads" / "raw"
    target = sheetmap_path(slug)
    files = sorted(raw.glob("*.pdf")) if raw.is_dir() else []

    if target.is_file() and not force:
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
        if isinstance(existing, dict) and _unchanged(existing, files):
            return existing

    payload = {
        "generated_at": _now(),
        "files": [_file_entry(pdf) for pdf in files],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
