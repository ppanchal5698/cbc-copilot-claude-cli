"""Project file layout on disk.

Mongo holds the structured data; the PDFs stay on the filesystem in the layout
the existing Python skills already expect - `projects/{slug}/uploads/raw/` and so
on. pdfplumber and PyMuPDF want real paths, and keeping this layout means every
agent and skill keeps working unchanged.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from api.config import settings

SUBDIRS = (
    "uploads/raw",
    "uploads/processed",
    "uploads/final",
    "extracted",
    "priced",
    "review",
)

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Lowercase, underscore-separated, ascii - matches the existing project names."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = _SLUG_STRIP.sub("_", ascii_name.lower()).strip("_")
    return slug[:60] or "project"


def project_dir(slug: str) -> Path:
    return settings.storage_root / slug


def scaffold(slug: str) -> Path:
    """Create the project tree. Idempotent - safe to call on an existing project."""
    root = project_dir(slug)
    for sub in SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    trail = root / "audit_trail.jsonl"
    if not trail.exists():
        trail.touch()
    return root


def raw_dir(slug: str) -> Path:
    return project_dir(slug) / "uploads" / "raw"


def unique_filename(directory: Path, filename: str) -> Path:
    """Never overwrite an uploaded document - raw uploads are immutable."""
    target = directory / filename
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return directory / f"{stem}_{stamp}{suffix}"


def relative(path: Path | str) -> str:
    """Store repo-relative paths so the database is portable across machines."""
    path = Path(path)
    try:
        return path.resolve().relative_to(settings.repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def absolute(stored: str) -> Path:
    path = Path(stored)
    return path if path.is_absolute() else (settings.repo_root / path).resolve()


def next_project_code(existing_codes: list[str]) -> str:
    """CBC-YYNNNN, continuing whatever series is already in the database."""
    year = datetime.now(timezone.utc).strftime("%y")
    prefix = f"CBC-{year}"
    used = [
        int(code[len(prefix) :])
        for code in existing_codes
        if code.startswith(prefix) and code[len(prefix) :].isdigit()
    ]
    return f"{prefix}{max(used) + 1 if used else 1:04d}"
