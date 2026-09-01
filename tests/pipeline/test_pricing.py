"""Pricing tests - the money math, the margin bands, and the tax rules.

Every number a customer sees comes out of calc-engine. If these pass, the
arithmetic on a CBC quote is right; if they fail, quotes are wrong.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import render_quote
from tests.shared import ROOT

BANDS = json.loads(
    (ROOT / "reference-library" / "margins" / "margin_framework.json").read_text(encoding="utf-8")
)


def test_sale_ea_is_cost_over_one_minus_margin(calc):
    line = calc.calculate_line(cost=100.0, margin=0.27)
    assert line["sale_ea"] == 136.99
    assert line["divisor"] == 0.73


def test_ext_is_sale_ea_times_quantity(calc):
    line = calc.calculate_line(cost=74.33, margin=0.27, quantity=3)
    assert line["sale_ea"] == 101.82
    assert line["ext_price"] == round(101.82 * 3, 2) == 305.46


@pytest.mark.parametrize(
    "product_type,margin,divisor",
    [
        ("commodity", 0.27, 0.73),
        ("restroom_partitions", 0.35, 0.65),
        ("specialty", 0.40, 0.60),
        ("custom_built", 0.25, 0.75),
        ("accessories", 0.56, 0.44),
    ],
)
def test_every_band_applies_its_own_divisor(calc, product_type, margin, divisor):
    result = calc.apply_margin(cost=100.0, product_type=product_type)
    assert result["default_margin"] == pytest.approx(margin)
    assert result["divisor"] == pytest.approx(divisor, abs=1e-9)
    assert result["sale_ea"] == pytest.approx(round(100.0 / divisor, 2), abs=0.01)


def test_accessories_band_is_56_percent_not_35():
    """Corrected in the 14 Jul session. A silent revert would misprice every accessory."""
    assert BANDS["accessories_derived"] == 0.56


def test_hager_worked_example_end_to_end(calc):
    """List 256.31 x locks tier 0.290 = cost 74.33 -> commodity sale 101.82."""
    cost = round(256.31 * 0.29, 2)
    assert cost == 74.33
    assert calc.apply_margin(cost=cost, product_type="commodity")["sale_ea"] == 101.82


def test_subtotals_and_grand_total_roll_up(calc):
    totals = calc.compute_totals(
        [
            {"group": "Door 01", "ext_price": 305.46},
            {"group": "Door 01", "sale_ea": 100.0, "quantity": 2},
            {"group": "Door 02", "ext_price": 40.0},
            {"group": "Accessories", "ext_price": 60.0},
        ]
    )
    groups = {g["group"]: g["subtotal"] for g in totals["groups"]}
    assert groups["Door 01"] == 505.46
    assert groups["Door 02"] == 40.0
    assert groups["Accessories"] == 60.0
    assert totals["subtotal"] == sum(groups.values()) == 605.46


@pytest.mark.parametrize(
    "state,rate", [("OH", 0.08), ("KY", 0.065), ("LA", 0.0), ("TX", 0.0), ("CA", 0.0)]
)
def test_sales_tax_only_for_ohio_and_kentucky(calc, state, rate):
    totals = calc.compute_totals([{"group": "g", "ext_price": 1000.0}], project_state=state)
    assert totals["tax_rate"] == rate
    assert totals["tax"] == round(1000.0 * rate, 2)
    assert totals["grand_total"] == round(1000.0 * (1 + rate), 2)


def test_unknown_state_leaves_tax_unresolved_rather_than_zero(calc):
    totals = calc.compute_totals([{"group": "g", "ext_price": 1000.0}])
    assert totals["project_state"] is None
    assert "UNRESOLVED" in totals["tax_note"]


def test_freight_is_tbd_at_estimate_stage(calc):
    totals = calc.compute_totals([{"group": "g", "ext_price": 100.0}])
    assert totals["freight"] is None
    assert "TBD" in totals["freight_note"]


def test_below_band_margin_is_flagged_not_blocked(calc):
    check = calc.validate_margin("commodity", 0.20)
    assert check["status"] == "fail"
    assert check["flag"] == "below_band"
    assert "deferred" in check["note"]


def test_override_without_a_reason_is_warned(calc):
    result = calc.apply_margin(cost=100.0, product_type="commodity", override_margin=0.15)
    assert result["overridden"] is True
    assert "warning" in result

    with_reason = calc.apply_margin(
        cost=100.0,
        product_type="commodity",
        override_margin=0.15,
        override_reason="bought via SecLock at higher cost",
    )
    assert "warning" not in with_reason


def test_invalid_inputs_are_rejected(calc):
    with pytest.raises(ValueError):
        calc.calculate_line(cost=100.0, margin=1.0)  # divide by zero
    with pytest.raises(ValueError):
        calc.calculate_line(cost=-1.0, margin=0.27)
    with pytest.raises(ValueError):
        calc.apply_margin(cost=100.0, product_type="not_a_band")


def test_quote_blocks_group_and_subtotal():
    blocks = render_quote.build_blocks(
        [
            {"group": "Door 01", "group_type": "door", "ext_price": 100.0},
            {"group": "Door 01", "group_type": "door", "ext_price": 50.5},
            {"group": "Restroom", "group_type": "accessories", "ext_price": 10.0},
            {"group": "Kitchen", "group_type": "frp", "ext_price": None},
        ]
    )
    assert [b["key"] for b in blocks] == ["door", "accessories", "frp"]
    assert blocks[0]["groups"][0]["subtotal"] == 150.5
    assert blocks[2]["groups"][0]["subtotal"] == 0.0, "an unpriced line must not break the roll-up"


def test_unit_weight_is_gone(calc):
    """Legacy truck-loading column, removed in the 14 Jul session."""
    line = calc.calculate_line(cost=100.0, margin=0.27, quantity=2)
    assert "unit_weight" not in line
    assert "total_weight" not in line


def test_an_adder_goes_on_the_list_price_not_the_cost():
    """The price book states the order outright, and the order is the money.

    "These are LIST adders. Multiply by the same category multiplier as the base
    item to get cost." A Hager 3500 storeroom lock lists at 256.31; the
    anti-microbial option adds 57.13 of *list*, which at the 0.29 lock tier is
    16.57 of cost. Adding it to the cost instead charges the full 57.13 and
    inflates the line by 40.56 before margin.
    """
    from cbc.core.calc import cost_from_list

    result = cost_from_list(256.31, 0.29, [{"name": "Anti-microbial", "list_adder": 57.13}])

    assert result["list_with_adders"] == 313.44
    assert result["cost"] == 90.90
    assert result["cost"] != round(256.31 * 0.29 + 57.13, 2)
    # An adder is a recorded act, so the line has to be able to show it.
    assert result["adders"][0]["cost_effect"] == 16.57


def test_a_line_with_no_adders_is_just_list_times_multiplier():
    from cbc.core.calc import cost_from_list

    assert cost_from_list(256.31, 0.29)["cost"] == round(256.31 * 0.29, 2)


def test_an_unpriced_adder_is_reported_not_treated_as_zero():
    """Only Hager's values are harvested; the rest are outstanding (NR-7).

    A missing adder must not read as "no adder" - that silently underprices.
    """
    from cbc.services.reference_library import find_adders

    result = find_adders(["Anti-microbial (26D finish only)", "electrification"])
    assert [m["list_adder"] for m in result["matched"]] == [57.13]
    assert result["unpriced"] == ["electrification"]


def test_both_finish_nomenclatures_read_the_same_finish():
    """A schedule mixes them: US26D, 626 and a bare 26D are one satin (NR-3)."""
    from cbc.services.reference_library import resolve_finish

    for spelling in ("US26D", "626", "26D", "us26d"):
        assert resolve_finish(spelling)["us_code"] == "US26D"


def test_us19_is_never_read_as_us26d():
    """They are different satins. A lockset in the wrong one is a return."""
    from cbc.services.reference_library import resolve_finish

    assert resolve_finish("US19")["us_code"] == "US19"
    assert resolve_finish("US19")["description"] != resolve_finish("US26D")["description"]


def test_a_numeric_two_finishes_share_is_flagged_not_guessed():
    """619 is US19 and US15 in CBC's own crosswalk.

    Picking whichever is listed first is exactly the confusion the crosswalk
    exists to prevent, so it comes back ambiguous with both candidates.
    """
    from cbc.services.reference_library import resolve_finish

    result = resolve_finish("619")
    assert result["ambiguous"] is True
    assert set(result["candidates"]) == {"US19", "US15"}
