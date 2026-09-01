"""Project file layout on disk.

Mongo holds the structured data; the PDFs stay on the filesystem in the layout
the existing Python skills already expect - `projects/{slug}/uploads/raw/` and so
on. pdfplumber and PyMuPDF want real paths, and keeping this layout means every
agent and skill keeps working unchanged.
"""
from __future__ import annotations

import os
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from cbc.config import settings

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


def purge_project(slug: str) -> None:
    """Remove a project's entire directory tree from disk.

    Human-initiated via the admin delete route — not something a pipeline agent
    does during a run. Idempotent when the folder is already gone.
    """
    if not slug or not slug.strip():
        raise ValueError("refusing to purge an empty project slug")

    root = project_dir(slug).resolve()
    storage_root = settings.storage_root.resolve()
    if root == storage_root:
        raise ValueError(f"refusing to delete the storage root: {storage_root}")
    if not root.is_relative_to(storage_root):
        raise ValueError(f"refusing to delete outside storage root: {root}")

    if root.exists():
        shutil.rmtree(root)


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


def safe_name(filename: str) -> str:
    """Reduce an uploaded filename to a bare name that cannot escape its directory.

    `UploadFile.filename` is whatever the client put in Content-Disposition, and
    nothing upstream strips it: `directory / "../../.claude/hooks/x.py"` resolves
    outside the project tree and `write_bytes` follows it. Both separators are
    normalised because a Windows-shaped path is only a separator on one platform
    and a very odd filename on the other.
    """
    name = os.path.basename(filename.replace("\\", "/")).strip()
    # A name that is only dots addresses a directory, not a file.
    return name if name.strip(".") else ""


def unique_filename(directory: Path, filename: str) -> Path:
    """Never overwrite an uploaded document - raw uploads are immutable."""
    target = directory / (safe_name(filename) or "upload")
    # Belt and braces: the basename above is what makes this true, and an assert
    # is what keeps it true if someone edits it.
    if not target.resolve().is_relative_to(directory.resolve()):
        raise ValueError(f"refusing to write outside {directory}: {filename!r}")
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return directory / f"{stem}_{stamp}{suffix}"


CHUNK = 1 << 20  # 1 MiB


async def receive_upload(file, target: Path, limit: int, magic: bytes | None = None) -> int:
    """Stream an upload to `target`, stopping the moment it exceeds `limit`.

    `await file.read()` with no argument pulls the whole body into memory before
    anything can check its size, so the 413 for a 2 GB POST arrived only after the
    process had already tried to hold 2 GB - or been OOM-killed, taking every
    in-flight request with it. Reading in chunks bounds the memory and yields the
    event loop between them.

    Returns the number of bytes written; raises ValueError on a body that is too
    large or does not start with `magic`, having removed the partial file.
    """
    size = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("wb") as handle:
            while chunk := await file.read(CHUNK):
                if size == 0 and magic and not chunk.startswith(magic):
                    raise ValueError("only PDF bid documents are accepted")
                size += len(chunk)
                if size > limit:
                    raise ValueError(f"file exceeds {limit // (1024 * 1024)} MB")
                handle.write(chunk)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    if size == 0:
        target.unlink(missing_ok=True)
        raise ValueError("the uploaded file is empty")
    return size


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


def code_prefix() -> str:
    return f"CBC-{datetime.now(timezone.utc).strftime('%y')}"


def highest_code_sequence(existing_codes: list[str], prefix: str) -> int:
    """The largest NNNN already issued under this prefix, or 0.

    Only used to seed the counter in `api.routers.projects`; allocation itself is
    atomic there. Deciding the next code from a scan of every project raced two
    concurrent creates into the same number and a duplicate-key 500.
    """
    used = [
        int(code[len(prefix) :])
        for code in existing_codes
        if code.startswith(prefix) and code[len(prefix) :].isdigit()
    ]
    return max(used) if used else 0
