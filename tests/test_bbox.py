"""Bounding-box provenance tests.

The review screen shows the estimator the real PDF page with a highlight over the
spot a value was read from. That only works if extraction persists coordinates,
so these tests guard the contract the viewer depends on.
"""
from __future__ import annotations

import sys
from pathlib import Path

import parse_schedule
from conftest import SCHEDULE_PAGE

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-servers"))

from _runtime import load_server  # noqa: E402

FIXTURE_PAGE_SIZE = {"width": 2592.0, "height": 1728.0}


def _valid_box(box) -> bool:
    return (
        isinstance(box, list)
        and len(box) == 4
        and all(isinstance(v, (int, float)) for v in box)
        and box[2] > box[0]
        and box[3] > box[1]
    )


def test_every_opening_carries_a_bbox_and_page_size(fixture_pdf):
    openings = parse_schedule.schedule_rows(str(fixture_pdf), SCHEDULE_PAGE)
    assert openings, "no openings extracted"
    for opening in openings:
        assert _valid_box(opening["bbox"]), f"bad bbox: {opening['bbox']}"
        assert opening["page_size"] == FIXTURE_PAGE_SIZE
        assert opening["cell_boxes"], "cell boxes are needed to tighten the highlight"


def test_bbox_sits_inside_the_page(fixture_pdf):
    size = parse_schedule.page_size(str(fixture_pdf), SCHEDULE_PAGE)
    for opening in parse_schedule.schedule_rows(str(fixture_pdf), SCHEDULE_PAGE):
        x0, y0, x1, y1 = opening["bbox"]
        assert 0 <= x0 < x1 <= size["width"]
        assert 0 <= y0 < y1 <= size["height"]


def test_highlight_is_tightened_to_the_schedule_row(fixture_pdf):
    """A CAD sheet puts unrelated notes on the same band; the highlight must not span them.

    All four Dutch Bros rows are the same schedule columns, so a correct highlight
    is the same width on each and starts at the same x.
    """
    openings = parse_schedule.schedule_rows(str(fixture_pdf), SCHEDULE_PAGE)
    widths = [round(o["bbox"][2] - o["bbox"][0], 1) for o in openings]
    lefts = [o["bbox"][0] for o in openings]
    assert len(set(widths)) == 1, f"inconsistent highlight widths: {widths}"
    assert len(set(lefts)) == 1, f"inconsistent highlight left edges: {lefts}"
    assert widths[0] < 400, "highlight is spanning unrelated sheet text"

    for opening in openings:
        raw = opening["row_bbox"]
        assert opening["bbox"][2] - opening["bbox"][0] <= raw[2] - raw[0]


def test_rows_are_vertically_ordered_and_do_not_overlap(fixture_pdf):
    boxes = [o["bbox"] for o in parse_schedule.schedule_rows(str(fixture_pdf), SCHEDULE_PAGE)]
    for upper, lower in zip(boxes, boxes[1:]):
        assert lower[1] >= upper[3] - 1, "schedule rows should stack, not overlap"


def test_pdf_tools_reports_page_size_and_row_boxes(fixture_pdf):
    pdf_tools = load_server("pdf-tools")

    size = pdf_tools.get_page_size(str(fixture_pdf), SCHEDULE_PAGE)
    assert size["width"] == FIXTURE_PAGE_SIZE["width"]
    assert size["height"] == FIXTURE_PAGE_SIZE["height"]
    assert size["page_count"] == 30

    page = pdf_tools.extract_tables(str(fixture_pdf), str(SCHEDULE_PAGE))["pages"][0]
    assert page["page_size"] == FIXTURE_PAGE_SIZE
    for row in page["rows"]:
        assert _valid_box(row["bbox"])
        assert len(row["cells"]) == len(row["cell_boxes"])


def test_page_size_rejects_a_page_out_of_range(fixture_pdf):
    import pytest

    with pytest.raises(ValueError):
        load_server("pdf-tools").get_page_size(str(fixture_pdf), 999)
