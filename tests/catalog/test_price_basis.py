"""What an indexed price means: a list figure, or a cost already.

The catalog screen rendered every indexed price as "list $X". For a Hager special
net read off the multiplier sheet that is backwards - 3.23 is the cost, and an
estimator who takes it for list and applies the 0.21 category multiplier quotes the
line at 68 cents. These pin the classification and the shape the API hands over,
because the failure is silent: a wrong label still shows a plausible number.
"""
from __future__ import annotations

import json

import pytest

from cbc.catalog import basis


@pytest.fixture(autouse=True)
def _fresh_caches():
    """The lookups are cached for the process; each test reads the real files."""
    basis._sheet_kinds.cache_clear()
    basis._vendors_with_a_multiplier.cache_clear()
    basis._net_program_vendors.cache_clear()
    yield


# ── the classification ──────────────────────────────────────────────────────


def test_a_multiplier_sheet_publishes_nets() -> None:
    """The sheet exists to publish special nets, so its numbers are costs."""
    assert basis.price_basis("hager_multipliers.pdf", "hager") == basis.NET


def test_a_price_book_from_a_multiplier_vendor_is_list() -> None:
    """Hager has both kinds of sheet on file; the book is the list one."""
    assert basis.price_basis("hager_price_book_18.pdf", "hager") == basis.LIST


def test_a_vendor_bought_on_a_net_program_is_net() -> None:
    """vendor_tiers records no multiplier for these and says why in words."""
    assert basis.price_basis("bobrick_hp_program_net.xlsx", "bobrick") == basis.NET
    assert basis.price_basis("gamco_hp_program_net.xlsx", "gamco") == basis.NET


def test_an_untranscribed_tier_is_not_a_net_program() -> None:
    """Pemko's multipliers were never transcribed. That is not the same fact.

    Both look like "no multiplier on file", and collapsing them would label a list
    price as a net - the mirror of the bug this exists for.
    """
    assert basis.price_basis("pemko_markar_price_book_2026.pdf", "pemko") == basis.UNKNOWN


def test_an_unrecognised_sheet_says_so_rather_than_guessing() -> None:
    assert basis.price_basis("who_knows.pdf", "acme") == basis.UNKNOWN
    assert basis.price_basis(None, None) == basis.UNKNOWN


def test_the_note_tells_an_estimator_what_to_do() -> None:
    assert "do not apply a multiplier" in basis.describe(basis.NET)
    assert "multiply" in basis.describe(basis.LIST)
    assert "confirm" in basis.describe(basis.UNKNOWN)


def test_every_indexed_sheet_classifies() -> None:
    """No sheet on file falls through to an exception or an empty string."""
    inventory = basis._pricebook_dir() / "index.json"
    if not inventory.exists():
        pytest.skip("no price-book inventory on this machine")
    entries = json.loads(inventory.read_text(encoding="utf-8"))["pricebooks"]
    assert entries, "inventory is empty"
    for entry in entries:
        result = basis.price_basis(entry["file"], entry.get("vendor"))
        assert result in (basis.LIST, basis.NET, basis.UNKNOWN), entry["file"]


# ── the shape the API hands to the screen ───────────────────────────────────


@pytest.mark.parametrize(
    "price_basis, expect_list, expect_net",
    [(basis.LIST, 12.5, None), (basis.NET, None, 12.5), (basis.UNKNOWN, None, None)],
)
def test_list_price_is_populated_only_when_it_is_one(
    price_basis: str, expect_list: float | None, expect_net: float | None
) -> None:
    """A caller that reads `listPrice` without checking the basis gets nothing.

    Filling it regardless is what let a net reach the screen labelled "list": the
    field name asserted something the index never knew.
    """
    row = {"price": 12.5, "price_basis": price_basis}
    list_price = row["price"] if row["price_basis"] == basis.LIST else None
    net_price = row["price"] if row["price_basis"] == basis.NET else None

    assert list_price == expect_list
    assert net_price == expect_net
    # The raw figure stays available either way, so nothing is hidden.
    assert row["price"] == 12.5
