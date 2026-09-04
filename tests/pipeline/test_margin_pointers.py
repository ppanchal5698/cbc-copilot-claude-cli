"""B-16: margin prose points at JSON; DEFAULT_BANDS stays the fallback."""
from __future__ import annotations

from cbc.core.calc import DEFAULT_BANDS
from tests.shared import ROOT

PROSE = (
    ROOT / ".claude" / "agents" / "pricing-engineer.md",
    ROOT / ".claude" / "memory" / "margin_sheet.md",
    ROOT / ".claude" / "skills" / "apply-margin" / "SKILL.md",
    ROOT / ".claude" / "skills" / "apply-margin" / "references" / "margin_bands.md",
    ROOT / "docs" / "cbc_process_flow.md",
)


def test_inlined_process_flow_has_no_commodity_margin_table() -> None:
    text = (ROOT / "docs" / "cbc_process_flow.md").read_text(encoding="utf-8")
    assert "27%" not in text
    assert "0.27" not in text


def test_margin_prose_points_at_the_json() -> None:
    for path in PROSE:
        body = path.read_text(encoding="utf-8")
        assert "margin_framework.json" in body, path


def test_default_bands_commodity_is_unchanged() -> None:
    assert DEFAULT_BANDS["commodity"] == 0.27
