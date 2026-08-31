"""Reading products off a page.

Every test here is a defect that was actually in the extractor, found by looking at
what it produced from the real price books rather than at whether it ran. The
generic parser is deliberately structural - it reads "a tabular row with something
code-shaped and something money-shaped" - so these pin the structure, not any one
vendor's layout.
"""
from __future__ import annotations

import pytest

from cbc.catalog import extractors, validate
from cbc.catalog.models import ProductRecord

ROW = ["010108", 'BB1279 4-1/2" x 4-1/2" US26D', "4.42"]


# ── the part number an architect would actually specify ────────────────────


def test_the_code_comes_from_the_description_not_only_a_whole_cell() -> None:
    """The largest vendor in the corpus indexed with no part numbers at all.

    Hager prints `010108 | BB1279 4-1/2" x 4-1/2" US26D | 4.42`. Testing each whole
    cell found nothing: the leading number was dismissed as "purely a number" and
    the description failed the pattern because of its spaces. Exact SKU lookup for
    75% of CBC's volume silently missed every time.
    """
    assert extractors._code_in(ROW) == "BB1279"


def test_a_numeric_series_number_is_a_part_number() -> None:
    """CLAUDE.md: architects specify "Hager 3400 is grade 1, 3500 is grade 2"."""
    assert extractors._code_in(["000091", '3553 2-3/4" US26D WTN SCC KD ASA']) == "3553"


def test_the_internal_item_number_is_only_a_fallback() -> None:
    """An estimator searches for 3553, not for Hager's stock number 000091."""
    cells = ["000091", '3553 2-3/4" US26D WTN']
    assert extractors._code_in(cells) == "3553"
    # With no manufacturer part on the row, the item number is better than nothing.
    assert extractors._code_in(["035528", "12.40"]) == "035528"


@pytest.mark.parametrize("not_a_code", ["44", "2026", "4.42", "800-325-9995"])
def test_page_numbers_years_prices_and_phone_numbers_are_not_part_numbers(not_a_code) -> None:
    assert extractors._code_in([not_a_code, "something else"]) != not_a_code


# ── boilerplate is not a product ───────────────────────────────────────────


def test_a_prose_line_is_not_a_product() -> None:
    """Terms-and-conditions pages carry prices and phone numbers.

    Reading them as products put 6 117 rows of boilerplate into the index and
    buried the real parts underneath them.
    """
    prose = ["Orders with a net value of less than $250.00 will be invoiced a $50.00 flat fee."]
    assert extractors._record_from_cells(prose, "hager", 3) is None


def test_a_phone_number_line_is_not_a_product() -> None:
    assert extractors._record_from_cells(["800-325-9995 (main phone)"], "hager", 3) is None


def test_a_real_table_row_is_a_product() -> None:
    record = extractors._record_from_cells(ROW, "hager", 18)
    assert record is not None
    assert record.product_code == "BB1279"
    assert record.price == 4.42
    assert record.page_number == 18
    assert record.raw_text, "the row as read, so a bad parse is auditable"


# ── two products on one visual row ─────────────────────────────────────────


def test_a_two_column_row_becomes_two_products() -> None:
    """Hager prints two product tables side by side.

    Clustering by vertical position welds them into one row, which pairs a part
    number from the left column with a price from the right - a wrong price against
    a real part number, which is the worst output this system can produce.
    """
    row = ['3550 2-3/8" US26D WTN SC', "034632", '3553 2-3/4" US10B WTN SC', "000096"]
    groups = extractors._split_columns(row)

    assert len(groups) == 2
    assert extractors._code_in(groups[0]) == "3550"
    assert extractors._code_in(groups[1]) == "3553"


def test_a_single_product_row_is_not_split() -> None:
    """The obvious guess - split on a wide gap - is wrong here, and this is why.

    Measured over seven sample pages of the Hager book the median gap *inside* a
    row is 94 pt while the gutter between the two columns is 53 pt. The gutter is
    narrower than the spacing it would have to beat, so the split is on the
    repeating pattern instead: one description cell per product.
    """
    assert extractors._split_columns(ROW) == [ROW]


# ── prices ─────────────────────────────────────────────────────────────────


def test_the_price_is_the_money_shaped_number_not_a_dimension() -> None:
    assert extractors._price_in('BB1279 4-1/2" x 4-1/2" US26D | 4.42') == 4.42
    assert extractors._price_in("1,234.56") == 1234.56
    assert extractors._price_in("no numbers here") is None


def test_a_row_with_no_price_is_still_a_product() -> None:
    """An unpriced line is a MANUAL item, not a row to discard (NFR-2)."""
    record = extractors._record_from_cells(["ECBB1100", "NRP hinge"], "hager", 81)
    assert record is not None and record.price is None


# ── validation ─────────────────────────────────────────────────────────────


def test_a_running_header_is_dropped() -> None:
    header = [
        ProductRecord("hager", page, "PL2026", "PRICE LIST 2026", None, None, None, None)
        for page in range(1, 9)
    ]
    kept, rejected = validate.clean(header)
    assert kept == []
    assert rejected["running_header_or_footer"] == 8


def test_a_year_in_a_price_column_is_not_a_price() -> None:
    assert validate.valid_price(2026.0) is False
    assert validate.valid_price(42.10) is True
    assert validate.valid_price(None) is True, "unpriced is honest, not invalid"
    assert validate.valid_price(-5.0) is False


def test_the_same_part_twice_on_one_page_is_indexed_once() -> None:
    twice = [ProductRecord("hager", 12, "BB1279", "Hinge", None, None, 4.42, "EA")] * 2
    kept, rejected = validate.clean(twice)
    assert len(kept) == 1 and rejected["duplicate_on_page"] == 1


def test_the_same_part_on_two_pages_is_kept_twice() -> None:
    """Different pages are different listings - sizes, finishes, quantities."""
    pages = [
        ProductRecord("hager", 12, "BB1279", "Hinge US26D", None, None, 4.42, "EA"),
        ProductRecord("hager", 30, "BB1279", "Hinge US10", None, None, 5.10, "EA"),
    ]
    kept, _ = validate.clean(pages)
    assert len(kept) == 2


def test_ocr_noise_is_rejected() -> None:
    noise = [ProductRecord("hager", 1, None, "|~+*/\\_ ,,,", "###@@@", None, None, None)]
    kept, rejected = validate.clean(noise)
    assert kept == [] and rejected["unreadable"] == 1


# ── choosing an adapter ────────────────────────────────────────────────────


def test_the_adapter_matches_the_file_type(tmp_path) -> None:
    assert extractors.choose(tmp_path / "sheet.xlsx") is extractors.extract_spreadsheet
    with pytest.raises(ValueError, match="no extractor"):
        extractors.choose(tmp_path / "notes.docx")


# ── delimited (CSV / TSV) sheets ────────────────────────────────


def test_a_delimited_sheet_gets_the_csv_adapter(tmp_path) -> None:
    assert extractors.choose(tmp_path / "multiplier.csv") is extractors.extract_csv
    assert extractors.choose(tmp_path / "cross.tsv") is extractors.extract_csv


def test_a_csv_net_sheet_is_read(tmp_path) -> None:
    """A vendor exports the net sheet as CSV; it indexes row-for-row like a spreadsheet."""
    sheet = tmp_path / "bobrick_net.csv"
    sheet.write_text(
        "part,description,list,net\n"
        "B-2888,Bobrick surface dispenser,120.00,72.00\n"
        "B-4388,Bobrick recessed dispenser,210.50,126.30\n",
        encoding="utf-8",
    )
    result = extractors.extract_csv(sheet, "bobrick")
    priced = {r.product_code: r.price for r in result.records}
    assert priced.get("B-2888") == 72.00
    assert priced.get("B-4388") == 126.30
    assert result.pages_read == 1


def test_a_semicolon_delimited_csv_is_sniffed(tmp_path) -> None:
    """European Excel exports use ';'. The delimiter is detected, not assumed."""
    sheet = tmp_path / "vendor.csv"
    sheet.write_text(
        "part;description;net\n"
        "B-2888;Bobrick dispenser;72.00\n"
        "B-4388;Bobrick recessed;126.30\n"
        "B-6699;Bobrick grab bar;41.10\n",
        encoding="utf-8",
    )
    result = extractors.extract_csv(sheet, "bobrick")
    assert any(r.product_code == "B-2888" and r.price == 72.00 for r in result.records)


def test_a_csv_with_a_utf8_bom_is_read(tmp_path) -> None:
    """Excel's 'CSV UTF-8' writes a BOM; utf-8-sig strips it so the first code is clean."""
    sheet = tmp_path / "bom.csv"
    sheet.write_bytes("part,net\nB-2888,72.00\n".encode("utf-8-sig"))
    result = extractors.extract_csv(sheet, "bobrick")
    assert any(r.product_code == "B-2888" for r in result.records)


# ── rendered pages must not land beside the drawings ───────────────────────


def test_a_rendered_page_defaults_to_the_cache_not_the_source_directory(tmp_path) -> None:
    """It used to default to the PDF's own directory.

    On a real autopilot run that dropped `1_Architectural_p12_200dpi.png` into
    `projects/{slug}/uploads/raw/`, where raw uploads are immutable
    (.claude/rules/file-safety.md).
    """
    from cbc.core import pdfpages

    raw = tmp_path / "uploads" / "raw"
    raw.mkdir(parents=True)
    assert pdfpages._writable_target(raw / "plans.pdf", None) == pdfpages.RENDER_CACHE


@pytest.mark.parametrize("protected", ["pricebooks", "reference-library"])
def test_read_only_reference_data_is_refused(protected: str) -> None:
    """pricebooks/ is mounted :ro on the worker; the failure should say why."""
    from cbc.core import pdfpages

    with pytest.raises(ValueError, match="read-only reference data"):
        pdfpages._writable_target(
            pdfpages.ROOT / "pricebooks" / "hager.pdf", pdfpages.ROOT / protected
        )
    with pytest.raises(ValueError, match="read-only reference data"):
        pdfpages._writable_target(
            pdfpages.ROOT / "pricebooks" / "hager.pdf", pdfpages.ROOT / protected / "pages"
        )


def test_writing_into_uploads_raw_is_refused_even_when_asked(tmp_path) -> None:
    """The guard is here because the PreToolUse hook cannot see this write:
    it happens inside PyMuPDF, not through Write or Bash."""
    from cbc.core import pdfpages

    raw = tmp_path / "uploads" / "raw"
    raw.mkdir(parents=True)
    with pytest.raises(ValueError, match="immutable"):
        pdfpages._writable_target(raw / "plans.pdf", raw)


def test_an_ordinary_output_directory_is_allowed(tmp_path) -> None:
    from cbc.core import pdfpages

    processed = tmp_path / "uploads" / "processed"
    assert pdfpages._writable_target(tmp_path / "plans.pdf", processed) == processed.resolve()
