"""The search index: schema, search, lifecycle.

These run against a real SQLite file rather than in memory, because the things most
likely to break are the things a memory database does not have: WAL, the `-shm`
file, foreign-key cascade across a reopened connection, and a second connection
reading while the first writes.
"""
from __future__ import annotations

import sqlite3

import pytest

from catalog_index import db, registry, search
from catalog_index.models import ProductRecord, looks_like_code, normalize_code


@pytest.fixture()
def index(tmp_path):
    connection = db.initialise(tmp_path / "catalog.sqlite3")
    try:
        yield connection
    finally:
        connection.close()


def _catalog(connection, vendor="hager", file_name="hager_price_book_18.pdf") -> str:
    catalog_id, needed = registry.register(
        connection, vendor=vendor, file_name=file_name, hash_hex="h" + vendor, page_count=10
    )
    assert needed
    return catalog_id


def _load(connection, catalog_id, records, extractor="table") -> int:
    build_id, staged = registry.stage(connection, catalog_id, records, version=1)
    assert staged == len(records)
    return registry.activate(connection, catalog_id, build_id, extractor=extractor)


HAGER = [
    ProductRecord("hager", 12, "150CX18", "Full Mortise Hinge 4.5 x 4.5",
                  "Heavy duty stainless steel ball bearing hinge", "hinges", 42.10, "EA", "raw a"),
    ProductRecord("hager", 44, "3510", "Grade 2 Storeroom Lock",
                  "Cylindrical storeroom lock US26D", "locks", 188.00, "EA", "raw b"),
]
BOBRICK = [
    ProductRecord("bobrick", 7, "B-2888", "Surface Mounted Paper Towel Dispenser",
                  "Stainless steel satin finish", "accessories", 119.30, "EA", "raw c"),
    ProductRecord("bobrick", 9, "B-6806x36", "Grab Bar 36 inch",
                  "1-1/2 inch stainless steel grab bar peened", "accessories", 66.75, "EA", "raw d"),
]


# ── normalization ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("written", ["B-2888", "b2888", "B 2888", "b-2888 ", "B.2888"])
def test_every_way_of_writing_a_part_number_normalizes_the_same(written: str) -> None:
    """The drawing, the estimator and the price book all spell it differently."""
    assert normalize_code(written) == "B2888"


@pytest.mark.parametrize("query, expected", [
    ("150CX18", True), ("B-2888", True), ("3510", True),
    ("hinge", False), ("door lock", False), ("ab", False), ("", False),
])
def test_code_detection_does_not_mistake_words_for_part_numbers(query, expected) -> None:
    assert looks_like_code(query) is expected


# ── the FTS query is built, never interpolated ─────────────────────────────


@pytest.mark.parametrize("hostile", ['"', 'a" OR b', "NEAR(a b)", "*", "a*", 'x" AND "y'])
def test_hostile_input_cannot_become_fts_syntax(index, hostile: str) -> None:
    """MATCH is a query language. Raw input in it is the same bug as raw SQL."""
    catalog_id = _catalog(index)
    _load(index, catalog_id, HAGER)

    # Must not raise sqlite3.OperationalError ("fts5: syntax error near ...").
    result = search.search(index, hostile)
    assert isinstance(result["results"], list)


def test_a_quoted_token_still_matches_its_word(index) -> None:
    catalog_id = _catalog(index)
    _load(index, catalog_id, HAGER)
    assert search.search(index, "storeroom")["count"] == 1


# ── the two search tiers ───────────────────────────────────────────────────


def test_exact_part_number_wins_outright(index) -> None:
    catalog_id = _catalog(index, "bobrick", "bobrick_price_list.pdf")
    _load(index, catalog_id, BOBRICK)

    top = search.search(index, "b2888")["results"][0]
    assert top["product_code"] == "B-2888"
    assert top["relevance_score"] == 1.0
    assert top["page_number"] == 7, "provenance travels with the result (NFR-3)"


def test_hyphenated_codes_survive_tokenization(index) -> None:
    """`tokenchars` is what keeps B-2888 one token instead of 'b' and '2888'."""
    catalog_id = _catalog(index, "bobrick", "bobrick_price_list.pdf")
    _load(index, catalog_id, BOBRICK)
    assert search.search(index, "B-2888")["count"] >= 1


def test_prefix_search_finds_a_partial_code(index) -> None:
    catalog_id = _catalog(index)
    _load(index, catalog_id, HAGER)
    assert any(r["product_code"] == "150CX18" for r in search.search(index, "150CX")["results"])


def test_multiple_keywords_rank_by_relevance(index) -> None:
    catalog_id = _catalog(index, "bobrick", "bobrick_price_list.pdf")
    _load(index, catalog_id, BOBRICK)

    results = search.search(index, "stainless steel grab bar")["results"]
    assert results, "no hits for a plain description search"
    assert results[0]["product_code"] == "B-6806x36"


def test_filters_narrow_the_search(index) -> None:
    _load(index, _catalog(index), HAGER)
    _load(index, _catalog(index, "bobrick", "bobrick_price_list.pdf"), BOBRICK)

    both = search.search(index, "stainless")
    assert both["count"] >= 2
    only = search.search(index, "stainless", vendor="bobrick")
    assert {r["vendor"] for r in only["results"]} == {"bobrick"}


def test_a_miss_says_so_instead_of_guessing(index) -> None:
    """NFR-2: never substitute the nearest stock part."""
    _load(index, _catalog(index), HAGER)
    result = search.search(index, "definitely-not-a-real-part-xyz")
    assert result["count"] == 0
    assert "MANUAL cut-off" in result["note"]


def test_the_same_part_on_many_pages_collapses_to_one_result(index) -> None:
    catalog_id = _catalog(index)
    repeated = [
        ProductRecord("hager", page, "150CX18", "Full Mortise Hinge", "hinge", "hinges", 42.10, "EA")
        for page in (12, 30, 61)
    ]
    _load(index, catalog_id, repeated)

    results = search.search(index, "150CX18")["results"]
    assert len(results) == 1, "three pages of the same part is one product"
    assert sorted(results[0]["also_on_pages"]) == [30, 61]


def test_the_result_limit_is_enforced(index) -> None:
    catalog_id = _catalog(index)
    _load(index, catalog_id, [
        ProductRecord("hager", 1, f"HINGE{n:04d}", f"Hinge {n}", "steel hinge", "hinges", 1.0, "EA")
        for n in range(200)
    ])
    assert search.search(index, "hinge", limit=5)["count"] == 5
    assert search.search(index, "hinge", limit=10_000)["count"] <= search.MAX_LIMIT


# ── lifecycle ──────────────────────────────────────────────────────────────


def test_an_unchanged_reupload_is_not_reindexed(index) -> None:
    catalog_id, first = registry.register(
        index, vendor="hager", file_name="h.pdf", hash_hex="same")
    _load(index, catalog_id, HAGER)
    again_id, again = registry.register(
        index, vendor="hager", file_name="h.pdf", hash_hex="same")

    assert first is True
    assert again_id == catalog_id and again is False, "re-read a book that did not change"


def test_a_changed_file_is_reindexed(index) -> None:
    catalog_id, _ = registry.register(index, vendor="hager", file_name="h.pdf", hash_hex="v1")
    _load(index, catalog_id, HAGER)
    _, needed = registry.register(index, vendor="hager", file_name="h.pdf", hash_hex="v2")
    assert needed is True


def test_a_staged_build_is_not_searchable_until_it_is_activated(index) -> None:
    """The requirement is that a partial index is never exposed."""
    catalog_id = _catalog(index)
    build_id, _ = registry.stage(index, catalog_id, HAGER, version=1)

    assert search.search(index, "150CX18")["count"] == 0, "staged rows leaked into search"

    registry.activate(index, catalog_id, build_id, extractor="table")
    assert search.search(index, "150CX18")["count"] == 1


def test_a_catalog_is_not_searchable_until_its_status_is_ready(index) -> None:
    catalog_id = _catalog(index)
    _load(index, catalog_id, HAGER)
    registry.set_status(index, catalog_id, "processing")
    assert search.search(index, "150CX18")["count"] == 0
    registry.set_status(index, catalog_id, "ready")
    assert search.search(index, "150CX18")["count"] == 1


def test_activating_an_empty_build_is_refused(index) -> None:
    """An extractor that found nothing must not silently empty a live catalog."""
    catalog_id = _catalog(index)
    _load(index, catalog_id, HAGER)

    empty_build, rows = registry.stage(index, catalog_id, [], version=2)
    assert rows == 0
    with pytest.raises(ValueError, match="staged no rows"):
        registry.activate(index, catalog_id, empty_build, extractor="table")

    assert search.search(index, "150CX18")["count"] == 1, "the old catalog survived"


# ── replacement ────────────────────────────────────────────────────────────


def test_the_old_catalog_stays_searchable_while_the_new_one_builds(index) -> None:
    catalog_id = _catalog(index)
    _load(index, catalog_id, HAGER)

    replacement = [ProductRecord("hager", 15, "150CX18", "Full Mortise Hinge",
                                 "revised 2027 listing", "hinges", 47.55, "EA")]
    build_id, _ = registry.stage(index, catalog_id, replacement, version=2)

    live = search.search(index, "150CX18")["results"][0]
    assert live["price"] == 42.10, "the old price vanished before the new one landed"

    registry.activate(index, catalog_id, build_id, extractor="table")
    now = search.search(index, "150CX18")["results"][0]
    assert now["price"] == 47.55 and now["page_number"] == 15


def test_a_failed_build_leaves_the_previous_version_live(index) -> None:
    catalog_id = _catalog(index)
    _load(index, catalog_id, HAGER)
    build_id, _ = registry.stage(index, catalog_id, [
        ProductRecord("hager", 1, "NEW1", "New", "new", "hinges", 1.0, "EA")], version=2)

    registry.discard_build(index, build_id)  # validation rejected it
    with pytest.raises(ValueError):
        registry.activate(index, catalog_id, build_id, extractor="table")

    assert search.search(index, "150CX18")["count"] == 1
    assert search.search(index, "NEW1")["count"] == 0


def test_replacement_leaves_no_rows_from_the_previous_version(index) -> None:
    catalog_id = _catalog(index)
    _load(index, catalog_id, HAGER)
    build_id, _ = registry.stage(index, catalog_id, [
        ProductRecord("hager", 1, "ONLY", "Only part", "the new sheet", "hinges", 5.0, "EA")],
        version=2)
    registry.activate(index, catalog_id, build_id, extractor="table")

    assert search.search(index, "3510")["count"] == 0, "a discontinued part is still searchable"
    assert db.integrity_report(index)["ok"]


# ── deletion ───────────────────────────────────────────────────────────────


def test_deleting_a_catalog_removes_every_trace_of_it(index) -> None:
    """The core requirement: no orphaned search records."""
    hager = _catalog(index)
    bobrick = _catalog(index, "bobrick", "bobrick_price_list.pdf")
    _load(index, hager, HAGER)
    _load(index, bobrick, BOBRICK)

    report = registry.delete(index, bobrick)

    assert report["removed"] == 2 and report["orphans"] == 0
    assert search.search(index, "B-2888")["count"] == 0
    assert search.search(index, "grab bar")["count"] == 0
    assert search.search(index, "150CX18")["count"] == 1, "the other vendor was collateral damage"

    integrity = db.integrity_report(index)
    assert integrity["ok"], integrity["problems"]
    assert integrity["products"] == 2


def test_deleting_a_catalog_mid_build_leaves_no_staged_rows(index) -> None:
    catalog_id = _catalog(index)
    _load(index, catalog_id, HAGER)
    registry.stage(index, catalog_id, HAGER, version=2)

    registry.delete(index, catalog_id)

    assert index.execute("SELECT count(*) FROM products_staging").fetchone()[0] == 0


def test_deleting_something_that_is_not_there_is_not_an_error(index) -> None:
    """Job retries have to be idempotent."""
    report = registry.delete(index, "does-not-exist")
    assert report["removed"] == 0 and report["orphans"] == 0


# ── the file itself ────────────────────────────────────────────────────────


def test_readers_cannot_write(tmp_path) -> None:
    writer = db.initialise(tmp_path / "catalog.sqlite3")
    catalog_id = _catalog(writer)
    _load(writer, catalog_id, HAGER)

    reader = db.connect(tmp_path / "catalog.sqlite3", readonly=True)
    try:
        assert reader.execute("SELECT count(*) FROM products").fetchone()[0] == 2
        with pytest.raises(sqlite3.OperationalError):
            reader.execute("DELETE FROM products")
    finally:
        reader.close()
        writer.close()


def test_a_reader_sees_a_write_without_being_blocked_by_it(tmp_path) -> None:
    """WAL: the point of it is that the pricing pass keeps searching while a
    catalog indexes. `query_only` rather than `mode=ro` is what makes a reader
    able to open a WAL database at all."""
    path = tmp_path / "catalog.sqlite3"
    writer = db.initialise(path)
    reader = db.connect(path, readonly=True)
    try:
        assert writer.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        catalog_id = _catalog(writer)
        _load(writer, catalog_id, HAGER)
        assert search.search(reader, "150CX18")["count"] == 1
    finally:
        reader.close()
        writer.close()


def test_the_index_refuses_an_unsafe_filesystem(tmp_path, monkeypatch) -> None:
    """9p/NFS/EFS do not give SQLite dependable locking; the failure is corruption."""
    monkeypatch.setattr(db, "filesystem_of", lambda path: "9p")
    monkeypatch.delenv("CATALOG_INDEX_ALLOW_UNSAFE_FS", raising=False)

    with pytest.raises(RuntimeError, match="9p"):
        db.connect(tmp_path / "catalog.sqlite3", readonly=False)


def test_the_unsafe_filesystem_check_can_be_overridden(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "filesystem_of", lambda path: "9p")
    monkeypatch.setenv("CATALOG_INDEX_ALLOW_UNSAFE_FS", "1")
    db.connect(tmp_path / "catalog.sqlite3", readonly=False).close()
