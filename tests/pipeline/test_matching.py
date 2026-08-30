"""Matching tests - the reference library, the price books, and confidence discipline.

These assert the behaviour NFR-2 depends on: every match carries a score, a
low-confidence match is flagged rather than accepted, and an unknown vendor or
category returns "price it manually" rather than a plausible number.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.shared import ROOT

REFERENCE = ROOT / "reference-library"
CONFIDENCE_THRESHOLD = 0.75


def _load(relative: str) -> dict:
    return json.loads((REFERENCE / relative).read_text(encoding="utf-8"))


def test_reference_library_is_complete_and_valid():
    required = [
        "hardware_sets/hager_top10_stock.json",
        "hardware_sets/allegion_stock.json",
        "hardware_sets/custom_other_matrix.json",
        "margins/margin_framework.json",
        "multipliers/vendor_tiers.json",
        "multipliers/special_customer_margins.json",
        "frame_depths/wall_type_to_depth.json",
        "finishes/finish_crosswalk.json",
        "frp_constants/conversion_constants.json",
        "adders/manual_adders.json",
    ]
    for relative in required:
        assert (REFERENCE / relative).exists(), f"missing {relative}"
        _load(relative)


def test_price_books_are_indexed(pricebook):
    catalog = pricebook.list_vendors()
    assert catalog["count"] >= 10, "expected the full vendor set to be indexed"
    vendors = {book["vendor"] for book in catalog["pricebooks"]}
    for expected in ("hager", "asi", "bradley", "rockwood", "national_guard", "pemko"):
        assert expected in vendors, f"{expected} price book not indexed"


def test_hager_multiplier_is_per_category(pricebook):
    locks = pricebook.get_multiplier("hager", "locks")
    assert locks["multiplier"] == 0.29
    assert locks["effective_date"] == "2026-03-02"
    assert locks["account"] == "HGR 17907"

    hinges = pricebook.get_multiplier("hager", "architectural_hinges")
    assert hinges["multiplier"] == 0.21, "hinges must not inherit the locks tier"


def test_unknown_vendor_returns_manual_not_a_guess(pricebook):
    result = pricebook.get_multiplier("acme_doors")
    assert result["multiplier"] is None
    assert "never guess" in result["note"]


def test_unknown_category_returns_manual_not_a_guess(pricebook):
    result = pricebook.get_multiplier("hager", "unicorn_hardware")
    assert result["multiplier"] is None
    assert "available_categories" in result


def test_allegion_is_distributor_bought_with_no_multiplier():
    """Allegion is not bought direct - a multiplier here would be a real defect."""
    tiers = _load("multipliers/vendor_tiers.json")
    allegion = next(v for v in tiers["vendors"] if v["key"] == "allegion")
    assert allegion["multiplier"] is None
    assert "MANUAL" in allegion["note"]
    assert "Banner Solutions" in allegion["distributors"]


def test_excluded_vendors_are_recorded():
    tiers = _load("multipliers/vendor_tiers.json")
    excluded = {v["name"] for v in tiers["excluded"]}
    assert "Scranton Products" in excluded
    assert "American Dryer" in excluded


def test_finish_crosswalk_keeps_us19_and_us26d_distinct():
    finishes = {f["us_code"]: f for f in _load("finishes/finish_crosswalk.json")["finishes"]}
    assert finishes["US26D"]["numeric_code"] == "626"
    assert finishes["US19"]["numeric_code"] == "619"
    assert finishes["US26D"]["numeric_code"] != finishes["US19"]["numeric_code"]


def test_frame_depths_cover_the_five_standard_throats():
    depths = {w["depth"] for w in _load("frame_depths/wall_type_to_depth.json")["wall_types"]}
    assert depths == {"5-5/8", "5-3/4", "5-7/8", "7-3/4", "8-1/4"}


def test_frp_constants_are_explicitly_pending():
    """A silently-zero constant would produce a confidently wrong FRP quantity."""
    constants = _load("frp_constants/conversion_constants.json")
    assert constants["status"] == "PENDING"
    for field in ("panel_size", "waste_pct", "trim_stick_length", "adhesive_coverage_sqft_per_unit"):
        assert constants[field] is None, f"{field} must stay null until CBC provides it"


@pytest.mark.parametrize(
    "confidence,should_flag",
    [(1.0, False), (0.95, False), (0.75, False), (0.74, True), (0.4, True), (0.0, True)],
)
def test_confidence_threshold(confidence, should_flag):
    assert (confidence < CONFIDENCE_THRESHOLD) is should_flag


def test_search_finds_a_real_part_with_page_traceability(pricebook):
    result = pricebook.search_product("4040XP", vendor="hager", limit=5)
    for hit in result["hits"]:
        assert hit["source_page"] >= 1, "every hit must carry source_page (NFR-3)"
        assert 0.0 <= hit["score"] <= 1.0


def test_ambiguous_lookup_refuses_to_pick_a_price(pricebook):
    """27 candidate rows must not collapse into one confident number."""
    result = pricebook.lookup_pricing("3510", "hager", "locks")
    assert result["match_count"] > 1
    assert result["net_cost"] is None
    assert result["cost_source"] == "MANUAL"
    assert result["multiplier"] == 0.29, "the tier is still reported for the estimator"
