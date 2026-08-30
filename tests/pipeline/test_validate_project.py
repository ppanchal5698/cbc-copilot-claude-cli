"""Artifact validation gates for the agentic pipeline."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.validate_project import (
    check_extraction,
    check_pricing,
    check_proposal,
    validate_job_artifacts,
)
from tests.shared import ROOT

from cbc_core import calc  # noqa: E402


def _write(project: str, relative: str, payload) -> Path:
    path = ROOT / "projects" / project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _good_opening(**overrides):
    base = {
        "door_number": "01",
        "size": "3670",
        "source_page": 14,
        "confidence": 0.9,
        "bbox": [10.0, 20.0, 100.0, 40.0],
        "page_size": {"width": 2592.0, "height": 1728.0},
        "hardware_set": "GROUP 1",
    }
    base.update(overrides)
    return base


@pytest.fixture
def validate_project(tmp_path, monkeypatch):
    project = "_validate_test"
    project_dir = ROOT / "projects" / project
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True)
    yield project
    shutil.rmtree(project_dir, ignore_errors=True)


def test_extraction_rejects_bare_array(validate_project):
    _write(validate_project, "extracted/door_schedule.json", [{"door_number": "01"}])
    problems, _ = check_extraction(validate_project)
    assert any("bare array" in p for p in problems)


def test_extraction_requires_bbox_and_confidence(validate_project):
    _write(
        validate_project,
        "extracted/door_schedule.json",
        {"openings": [{"door_number": "01", "size": "3070", "source_page": 14}]},
    )
    problems, _ = check_extraction(validate_project)
    assert any("bbox" in p for p in problems)
    assert any("confidence" in p for p in problems)


def test_extraction_passes_with_provenance(validate_project):
    _write(
        validate_project,
        "extracted/door_schedule.json",
        {"openings": [_good_opening()]},
    )
    problems, warnings = check_extraction(validate_project)
    assert not problems
    assert warnings  # soft fields still missing


def test_pricing_requires_line_envelope(validate_project):
    _write(validate_project, "priced/line_items.json", {"lines": []})
    problems, _ = check_pricing(validate_project)
    assert any("non-empty lines" in p for p in problems)


def test_pricing_requires_fields_on_each_line(validate_project):
    _write(
        validate_project,
        "priced/line_items.json",
        {
            "lines": [
                {
                    "description": "Hinge",
                    "cost": 1.0,
                    "sale_ea": 1.27,
                    "ext_price": 1.27,
                }
            ]
        },
    )
    problems, _ = check_pricing(validate_project)
    assert any("line_id" in p for p in problems)


def test_validate_job_artifacts_raises(validate_project):
    _write(validate_project, "extracted/door_schedule.json", {"openings": []})
    with pytest.raises(ValueError, match="artifact validation failed"):
        validate_job_artifacts("extract_bid_set", validate_project)


def test_compute_totals_treats_null_sale_as_unpriced(calc):
    totals = calc.compute_totals(
        [
            {"group": "01", "ext_price": None, "sale_ea": None, "quantity": 3},
            {"group": "01", "ext_price": 10.0},
        ]
    )
    groups = {g["group"]: g["subtotal"] for g in totals["groups"]}
    assert groups["01"] == 10.0
    assert totals["subtotal"] == 10.0


def test_match_and_price_prompt_uses_agent_tool_not_paths():
    from worker import prompts

    assert ".claude/agents/" not in prompts.MATCH_AND_PRICE
    assert "product-matcher" in prompts.MATCH_AND_PRICE
    assert "description" in prompts.PREAMBLE.lower()


def test_build_proposal_prompt_uses_agent_tool_not_paths():
    from worker import prompts

    assert ".claude/agents/" not in prompts.BUILD_PROPOSAL
    assert "quote-builder" in prompts.BUILD_PROPOSAL
