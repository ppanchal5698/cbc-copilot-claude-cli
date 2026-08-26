"""Runtime configuration for the CBC Ops-Hub API.

Values come from the environment (see .env.example). Everything has a working
local default so the service starts against docker-compose without setup.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _path(env_var: str, default: str) -> Path:
    raw = os.environ.get(env_var, default)
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


class Settings:
    """Process settings. Read once at import, overridable in tests."""

    def __init__(self) -> None:
        self.mongodb_uri = os.environ.get(
            "MONGODB_URI",
            "mongodb://cbc:cbc_local_dev@localhost:27017/cbc_opshub?authSource=admin",
        )
        self.mongodb_db = os.environ.get("MONGODB_DB", "cbc_opshub")
        self.repo_root = REPO_ROOT
        self.storage_root = _path("STORAGE_ROOT", "projects")
        self.pricebook_dir = _path("PRICEBOOK_DIR", "pricebooks")
        self.reference_dir = _path("REFERENCE_DIR", "reference-library")
        self.templates_dir = _path("TEMPLATES_DIR", "templates")
        self.cors_origins = [
            origin.strip()
            for origin in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
            if origin.strip()
        ]
        self.max_upload_mb = int(os.environ.get("MAX_UPLOAD_MB", "128"))

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
