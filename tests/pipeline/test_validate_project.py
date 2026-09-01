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


def test_extraction_takes_the_shapes_the_importer_takes(validate_project):
    """The gate must not refuse what sync would have imported cleanly.

    `_normalize_schedule_payload` has always accepted a bare array, and accepts
    a `lines` wrapper since a run wrote a complete schedule under that key. This
    check runs *before* sync, so anything it refuses never gets there - and it
    was failing whole pipelines over the word wrapping the array while every
    opening inside was well formed.

    The shape is tolerated; the contents are not. Each opening still goes
    through every per-opening check, which the assertions below pin.
    """
    for payload in (
        [_good_opening()],                    # bare array
        {"openings": [_good_opening()]},      # canonical
        {"lines": [_good_opening()]},         # the priced artifact's key
    ):
        _write(validate_project, "extracted/door_schedule.json", payload)
        problems, _ = check_extraction(validate_project)
        assert not problems, f"{payload!r} was refused: {problems}"

    # ... and a bad opening is still caught inside every one of those shapes.
    for payload in (
        [{"door_number": "01"}],
        {"openings": [{"door_number": "01"}]},
        {"lines": [{"door_number": "01"}]},
    ):
        _write(validate_project, "extracted/door_schedule.json", payload)
        problems, _ = check_extraction(validate_project)
        assert any("bbox" in p for p in problems), payload


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


def test_a_hand_added_opening_needs_no_drawing_page(validate_project):
    """A hand dryer nobody drew is still a line on the quote.

    Every drawing-provenance check fired on the estimator's own entry, reporting
    five problems against a healthy project - and the same demand one layer down
    made a pricing pass invent a page number to satisfy it (NFR-2).
    """
    _write(
        validate_project,
        "extracted/door_schedule.json",
        {
            "openings": [
                _good_opening(),
                {
                    "description": "Hand Dryer",
                    "qty": 1.0,
                    "confidence": 1.0,
                    "status": "by_hand",
                    "added_by_hand": True,
                    "confirmed_by": "admin@cbc.com",
                    "door_number": None,
                    "source_page": None,
                    "bbox": None,
                    "page_size": None,
                },
            ]
        },
    )
    problems, _ = check_extraction(validate_project)
    assert not problems, problems


def test_a_hand_added_opening_must_still_identify_itself(validate_project):
    _write(
        validate_project,
        "extracted/door_schedule.json",
        {"openings": [{"added_by_hand": True, "confidence": 1.0, "qty": 1.0}]},
    )
    problems, _ = check_extraction(validate_project)
    assert any("neither a door_number nor a description" in p for p in problems), problems


def test_a_drawing_opening_still_needs_its_provenance(validate_project):
    """Relaxing the hand-added case must not relax the drawing case."""
    _write(
        validate_project,
        "extracted/door_schedule.json",
        {"openings": [_good_opening(source_page=None, bbox=None)]},
    )
    problems, _ = check_extraction(validate_project)
    assert any("missing source_page" in p for p in problems), problems
    assert any("bbox" in p for p in problems), problems


def test_a_manual_line_may_not_carry_an_invented_cost(validate_project):
    """MANUAL means nobody could price it. A number there is one the pass made up.

    A real run returned 27 of 34 lines as MANUAL with round costs and details
    reading "Estimated standard cost for 36x84 HM door". A quote that looks
    complete and is invented is far worse than one that says what it does not
    know - and no wording in a prompt reliably prevents it (NFR-2).
    """
    _write(
        validate_project,
        "priced/line_items.json",
        {
            "lines": [
                _priced(
                    group="Door 01",
                    group_type="door",
                    part_number="HM-D3684",
                    description="HM door",
                    cost_source="MANUAL",
                    cost_source_detail="Estimated standard cost for 36x84 HM door",
                    cost=500.0,
                    source_page=14,
                )
            ]
        },
    )
    problems, _ = check_pricing(validate_project)
    assert any("carries a cost" in p for p in problems), problems


def test_a_manual_line_with_no_cost_is_fine(validate_project):
    _write(
        validate_project,
        "priced/line_items.json",
        {
            "lines": [
                _priced(
                    group="Door 01",
                    group_type="door",
                    part_number="HM-D3684",
                    description="HM door",
                    cost_source="MANUAL",
                    cost_source_detail="Custom size - vendor RFQ required",
                    cost=None,
                    source_page=14,
                )
            ]
        },
    )
    problems, _ = check_pricing(validate_project)
    assert not [p for p in problems if "carries a cost" in p], problems


def test_a_computed_cost_must_name_the_sheet_it_was_read_from(validate_project):
    """"Price based on Pemko catalog" names no page anyone can open.

    The same run put three different costs on one part and cited the bid set's
    door-schedule page for all of them. The catalog tools return a file name and
    a locator so this citation is available (NFR-3).
    """
    _write(
        validate_project,
        "priced/line_items.json",
        {
            "lines": [
                _priced(
                    part_number="PEMKO-8400",
                    cost_source="LIST_X_MULTIPLIER",
                    cost_source_detail="Price based on Pemko catalog",
                    cost=80.0,
                    source_page=14,
                )
            ]
        },
    )
    problems, _ = check_pricing(validate_project)
    assert any("names no price-book file" in p for p in problems), problems


def test_a_real_citation_passes(validate_project):
    _write(
        validate_project,
        "priced/line_items.json",
        {
            "lines": [
                _priced(
                    part_number="PEMKO-8400",
                    cost_source="LIST_X_MULTIPLIER",
                    cost_source_detail="pemko_markar_price_book_2026.pdf PDF p67 (printed p60)",
                    cost=80.0,
                    source_page=67,
                )
            ]
        },
    )
    problems, _ = check_pricing(validate_project)
    assert not [p for p in problems if "price-book file" in p], problems
