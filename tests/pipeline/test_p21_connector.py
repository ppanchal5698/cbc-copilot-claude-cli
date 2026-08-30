"""P21 connector contract tests."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp-servers" / "p21-connector"))

from server import check_freshness, lookup_last_po, search_item  # noqa: E402


def test_lookup_without_base_url_returns_manual_entry() -> None:
    result = lookup_last_po("BB1279", vendor="Hager")
    assert result["cost_source"] == "MANUAL"
    assert result["last_po_price"] is None


def test_search_without_base_url_is_empty() -> None:
    result = search_item("hinge")
    assert result["results"] == []
    assert result["connected"] is False


def test_freshness_under_six_months_is_usable() -> None:
    from datetime import date, timedelta

    recent = (date.today() - timedelta(days=30)).isoformat()
    result = check_freshness(recent)
    assert result["freshness_status"] == "fresh"
    assert result["usable"] is True


def test_freshness_over_three_years_is_stale() -> None:
    from datetime import date, timedelta

    old = (date.today() - timedelta(days=1200)).isoformat()
    result = check_freshness(old)
    assert result["freshness_status"] == "stale"
    assert result["usable"] is False
