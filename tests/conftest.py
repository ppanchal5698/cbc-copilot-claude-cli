"""Shared fixtures and path wiring for the CBC test suite.

All five MCP servers are called server.py, so they are loaded through
_runtime.load_server(), which imports each under a unique module name. A plain
`import server` would give whichever server was imported first.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

for extra in (
    ROOT / "mcp-servers",
    ROOT / ".claude" / "skills" / "extract-door-schedule" / "scripts",
    ROOT / ".claude" / "skills" / "generate-quotation" / "scripts",
):
    sys.path.insert(0, str(extra))

from _runtime import load_server  # noqa: E402

FIXTURE_PDF = (
    ROOT / "projects" / "dutch_bros_macarthur_2026" / "uploads" / "raw" / "1_Architectural.pdf"
)
SCHEDULE_PAGE = 14  # sheet A2.2 in the Dutch Bros fixture


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def fixture_pdf() -> Path:
    if not FIXTURE_PDF.exists():
        pytest.skip(f"test fixture not present: {FIXTURE_PDF}")
    return FIXTURE_PDF


@pytest.fixture(scope="session")
def calc():
    return load_server("calc-engine")


@pytest.fixture(scope="session")
def pricebook():
    return load_server("pricebook")


@pytest.fixture(scope="session")
def p21():
    return load_server("p21-connector")
