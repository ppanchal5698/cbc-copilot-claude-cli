"""Describing a catalog page without reading it wrongly.

The index this replaces pre-extracted every product row and got 37.8% of its
codes wrong - dates as part numbers, one vendor's sheet yielding nothing while
reporting success. PageIndex stores no prices at all, so the failure it must
avoid is different: sending a pricing pass to the wrong page, or citing a page
number an estimator cannot find in the book.
"""
from __future__ import annotations

import pytest

from cbc.pageindex.describe import describe_page, needs_a_second_look, page_lines
from cbc.pageindex.models import PageProfile

# The real Hager running header: printed number, date, url, then the section.
HAGER = PageProfile(
    title_source="line_index:3",
    printed_page_source="line_index:0",
    boilerplate=["www.hagerco.com", "03/01/2026"],
)

HAGER_PAGE = (
    "23\n03/01/2026\nwww.hagerco.com\nLocks - 3400 Series\n"
    "Strikes\nDescription\n"
    "3400 ANSI strike 1-1/4 x 4-7/8 US26D  $12.50\n"
    "3402 T-strike US10B  $14.75\n"
    "3400L lip strike  $16.00\n"
)


def test_the_profile_finds_the_section_title() -> None:
    assert describe_page(HAGER_PAGE, 297, HAGER).title == "Locks - 3400 Series"


def test_both_page_numbers_are_recorded() -> None:
    """The pair NFR-3 needs.

    Hager's PDF page 297 prints as "23" because numbering restarts per section.
    Across the real catalogs this is not an edge case - 775 of 1,216 pages print
    a number that differs from their PDF index. An estimator sent to "page 23" of
    a 744-page book cannot find the line without both.
    """
    entry = describe_page(HAGER_PAGE, 297, HAGER)
    assert entry.pdf_page == 297
    assert entry.printed_page == "23"
    assert entry.locator() == "PDF p297 (printed p23)"


def test_a_page_whose_numbers_agree_says_it_once() -> None:
    entry = describe_page("7\n03/01/2026\nwww.hagerco.com\nHinges\nBB1279  $9.00", 7, HAGER)
    assert entry.locator() == "p7"


def test_a_price_page_is_recognised_as_one() -> None:
    entry = describe_page(HAGER_PAGE, 297, HAGER)
    assert entry.has_prices
    assert entry.kind == "price_table"
    assert entry.confidence >= 0.9


def test_the_part_families_on_the_page_are_collected() -> None:
    """Routing, not reproduction: enough to know the 3400s live here."""
    assert "3400" in describe_page(HAGER_PAGE, 297, HAGER).code_prefixes


def test_finish_codes_are_not_part_families() -> None:
    """US26D is a finish (rule 7.5), and appears on nearly every price page.

    Left in, they crowd the real families out of the routing list entirely.
    """
    prefixes = describe_page(HAGER_PAGE, 297, HAGER).code_prefixes
    assert not [code for code in prefixes if code.startswith("US")], prefixes


def test_a_date_is_not_a_part_number() -> None:
    """183 dates were indexed as products by the extractor this replaces."""
    entry = describe_page("Effective 03/01/2026\n11/21/2019 revision\nNotes", 1, PageProfile())
    assert not [c for c in entry.code_prefixes if "/" in c or c in {"2026", "2019"}], entry.code_prefixes


def test_a_page_with_no_text_layer_is_not_described_as_read() -> None:
    """A scan gets a low score and a name that says so, not an invented summary."""
    entry = describe_page("", 5, HAGER)
    assert entry.kind == "diagram"
    assert entry.confidence <= 0.2
    assert needs_a_second_look(entry)


def test_a_well_read_page_needs_no_second_look() -> None:
    assert not needs_a_second_look(describe_page(HAGER_PAGE, 297, HAGER))


def test_boilerplate_is_kept_out_of_the_description() -> None:
    entry = describe_page(HAGER_PAGE, 297, HAGER)
    assert "hagerco.com" not in entry.description
    assert "03/01/2026" not in entry.description


def test_a_profile_that_does_not_fit_degrades_rather_than_lies() -> None:
    """Point a Hager profile at a page that is not Hager.

    It must not assert a title it did not find; the fallback is the page's own
    first line, and the score drops to say the title is inferred.
    """
    entry = describe_page("MODEL NUMBER\nASI WASHROOM ACCESSORIES\n0197  $210.00", 10, HAGER)
    assert entry.confidence <= 0.6


@pytest.mark.parametrize(
    "source, expected",
    [("line_index:3", "Locks - 3400 Series"), ("regex:^(Locks.*)$", "Locks - 3400 Series")],
)
def test_both_profile_grammars_resolve(source: str, expected: str) -> None:
    profile = PageProfile(title_source=source, boilerplate=HAGER.boilerplate)
    assert describe_page(HAGER_PAGE, 297, profile).title == expected


def test_an_unresolvable_rule_returns_nothing_rather_than_something() -> None:
    for bad in ("line_index:99", "line_index:not-a-number", "regex:([unclosed", "nonsense"):
        entry = describe_page(HAGER_PAGE, 297, PageProfile(title_source=bad))
        assert entry.title != "", "should fall back to the first line, not crash"
    assert describe_page("", 1, PageProfile(title_source="line_index:0")).title == ""


def test_a_spreadsheet_block_cites_its_sheet_and_rows() -> None:
    """Three of the fourteen catalogs are spreadsheets, where a page is a fiction."""
    entry = describe_page(
        "Program Net\nB-2888 Soap dispenser  $41.00",
        1,
        PageProfile(),
        sheet="Program Net",
        rows=[12, 260],
    )
    assert entry.locator() == "sheet Program Net rows 12-260"
    assert "B-2888" in entry.code_prefixes


def test_page_lines_drops_blanks_and_whitespace() -> None:
    assert page_lines("a\n\n   \n b \n") == ["a", "b"]
