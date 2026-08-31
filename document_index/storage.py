"""Versioned on-disk layout for deep-index artifacts."""
from __future__ import annotations

import os
import shutil
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from cbc_core.paths import repo_root

REPO_ROOT = repo_root()


def root_path() -> Path:
    configured = os.environ.get("DOCUMENT_INDEX_ROOT")
    if configured:
        return Path(configured)
    return REPO_ROOT / ".index" / "documents"


def normalise_effective(value: str | None) -> str:
    if value:
        return value.strip()
    return date.today().isoformat()


def document_dir(
    client_id: str,
    document_type: str,
    effective_date: str,
    document_id: str,
) -> Path:
    safe_client = client_id.strip().lower().replace("/", "_")
    safe_type = document_type.strip().lower().replace("/", "_")
    safe_date = effective_date.strip().replace("/", "-")
    return root_path() / safe_client / safe_type / safe_date / document_id


def allocate_document_id() -> str:
    return str(uuid.uuid4())


def link_source_pdf(source: Path, dest: Path) -> None:
    """Copy or hard-link the source PDF into the version folder."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    try:
        os.link(source, dest)
    except OSError:
        shutil.copy2(source, dest)


def write_json(path: Path, payload: object) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def read_json(path: Path) -> dict | list:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
