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

from cbc.core import calc  # noqa: E402


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
    from apps.worker import prompts

    assert ".claude/agents/" not in prompts.MATCH_AND_PRICE
    assert "product-matcher" in prompts.MATCH_AND_PRICE
    # The Agent-call contract moved out of PREAMBLE into DELEGATION_RULE when the
    # prompts gained a second mode, so assert on what a run is actually handed.
    delegating = prompts.preamble_for("projects/demo", delegates=True)
    assert "description" in delegating.lower()
    assert "subagent_type" in delegating


def test_a_provider_that_cannot_delegate_is_told_to_do_the_work_itself():
    """An Ollama run read the delegation instruction, could not follow it, and
    made seven tool calls in twelve minutes without writing an output file.

    The phases and their output files must survive into the solo prompt - only
    the means of carrying them out changes.
    """
    from apps.worker import prompts

    job = {"type": "match_and_price", "payload": {}}
    project = {"slug": "demo", "code": "CBC-1"}

    solo = prompts.build(job, project, delegates=False)
    assert "subagent_type" not in solo, "solo runs must not be told to delegate"
    assert "Do these yourself" in solo or "Do the work yourself" in solo
    # Same phases, same artefacts.
    assert "product-matcher" in solo and "pricing-engineer" in solo
    assert "priced/line_items.json" in solo

    delegating = prompts.build(job, project, delegates=True)
    assert "subagent_type" in delegating


def test_build_proposal_prompt_uses_agent_tool_not_paths():
    from apps.worker import prompts

    assert ".claude/agents/" not in prompts.BUILD_PROPOSAL
    assert "quote-builder" in prompts.BUILD_PROPOSAL


def _priced(**overrides):
    line = {
        "line_id": 1,
        "group": "accessories",
        "group_type": "accessories",
        "part_number": "10-0199-1-41",
        "description": "ASI Hand Dryer",
        "quantity": 1,
        "cost_source": "LIST_X_MULTIPLIER",
        "cost_source_detail": "asi_price_list.pdf p34",
        "source_page": None,
    }
    line.update(overrides)
    return line


def test_a_hand_added_accessory_needs_price_provenance_not_a_drawing_page(validate_project):
    """An accessory the estimator typed in has no page, and must not invent one.

    Requiring source_page on every priced line rejected a correctly priced hand
    dryer and failed the whole sync; on the retry the pass satisfied the rule by
    putting the hand dryer on the door-schedule page. A check whose cheapest
    escape is a fabricated citation is worse than the gap it closes (NFR-2).
    """
    _write(validate_project, "priced/line_items.json", {"lines": [_priced()]})
    problems, _ = check_pricing(validate_project)
    assert not any("source_page" in p for p in problems), problems


def test_an_accessory_with_no_trace_at_all_is_still_rejected(validate_project):
    _write(
        validate_project,
        "priced/line_items.json",
        {"lines": [_priced(cost_source_detail="")]},
    )
    problems, _ = check_pricing(validate_project)
    assert any("neither a source_page nor a cost_source_detail" in p for p in problems), problems


def test_a_door_line_still_must_name_its_page(validate_project):
    """Doors come off the schedule. That half of NFR-3 does not relax."""
    _write(
        validate_project,
        "priced/line_items.json",
        {
            "lines": [
                _priced(
                    group="Door 01",
                    group_type="door",
                    part_number="D-01",
                    description="HM door",
                    cost_source="MANUAL",
                    cost_source_detail="awaiting vendor RFQ",
                )
            ]
        },
    )
    problems, _ = check_pricing(validate_project)
    assert any("has no source_page" in p for p in problems), problems
