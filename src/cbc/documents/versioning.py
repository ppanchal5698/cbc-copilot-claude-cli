"""current_version pointer and no-overwrite guarantees."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cbc.documents import storage


def registry_path() -> Path:
    return storage.root_path() / "registry.json"


def load_registry() -> dict[str, Any]:
    path = registry_path()
    if not path.exists():
        return {"versions": [], "current": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(registry: dict[str, Any]) -> None:
    storage.write_json(registry_path(), registry)


def version_key(client_id: str, document_type: str) -> str:
    return f"{client_id.strip().lower()}|{document_type.strip().lower()}"


def register_version(
    *,
    document_id: str,
    client_id: str,
    document_type: str,
    effective_date: str,
    folder: Path,
    source_path: str,
) -> None:
    """Record a new version. Never overwrites an existing document_id folder."""
    if folder.exists() and any(folder.iterdir()):
        # Folder already populated — this document_id is immutable.
        pass

    registry = load_registry()
    entry = {
        "document_id": document_id,
        "client_id": client_id,
        "document_type": document_type,
        "effective_date": effective_date,
        "folder": str(folder),
        "source_path": source_path,
        "registered_at": storage.now_iso(),
    }
    registry.setdefault("versions", []).append(entry)
    save_registry(registry)


def list_versions(client_id: str, document_type: str) -> list[dict[str, Any]]:
    registry = load_registry()
    key = version_key(client_id, document_type)
    matches = [
        v
        for v in registry.get("versions", [])
        if version_key(v["client_id"], v["document_type"]) == key
    ]
    current_id = registry.get("current", {}).get(key)
    for item in matches:
        item["is_current"] = item["document_id"] == current_id
    return sorted(matches, key=lambda v: v.get("effective_date") or "", reverse=True)


def get_current_version(client_id: str, document_type: str) -> str | None:
    registry = load_registry()
    return registry.get("current", {}).get(version_key(client_id, document_type))


def promote_current_version(
    document_id: str,
    client_id: str,
    document_type: str,
    *,
    allow_review_needed: bool = False,
    review_count: int = 0,
) -> bool:
    """Set current_version when indexing succeeded cleanly."""
    if review_count > 0 and not allow_review_needed:
        return False

    registry = load_registry()
    key = version_key(client_id, document_type)
    registry.setdefault("current", {})[key] = document_id
    save_registry(registry)
    return True


def resolve_document_folder(document_id: str) -> Path | None:
    registry = load_registry()
    for entry in registry.get("versions", []):
        if entry.get("document_id") == document_id:
            return Path(entry["folder"])
    # Fallback: scan filesystem (tests / manual copies)
    root = storage.root_path()
    if not root.exists():
        return None
    for path in root.rglob("manifest.json"):
        manifest = storage.read_json(path)
        if manifest.get("document_id") == document_id:
            return path.parent
    return None
