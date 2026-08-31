"""Rebuild the whole index from the PDFs.

This is what makes the index disposable rather than precious. Delete the file, run
this, and the search index is back - because the vendor files are the source of
truth and nothing here is hand-maintained.

    python -m cbc.catalog.rebuild              # index anything new or changed
    python -m cbc.catalog.rebuild --force      # re-read everything
    python -m cbc.catalog.rebuild --verify     # report only, change nothing
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from cbc.catalog import db, pipeline, registry
from cbc.catalog.db import REPO_ROOT

log = logging.getLogger("cbc.catalog.rebuild")

INDEXABLE = {".pdf", ".xlsx", ".xlsm"}  # .xls is legacy; see extractors.choose


def catalogue_files(pricebook_dir: Path) -> list[dict[str, str]]:
    """What to index, from pricebooks/index.json - the inventory purchasing keeps.

    Files on disk that the inventory does not mention are indexed too, under a
    vendor guessed from the filename: a sheet nobody recorded is still a sheet an
    estimator will search for, and silently ignoring it is the worse failure.
    """
    entries: list[dict[str, str]] = []
    seen: set[str] = set()

    index_file = pricebook_dir / "index.json"
    if index_file.exists():
        for book in json.loads(index_file.read_text(encoding="utf-8")).get("pricebooks", []):
            if book.get("kind") == "multiplier_sheet":
                continue
            name = book.get("file")
            if not name or Path(name).suffix.lower() not in INDEXABLE:
                continue
            seen.add(name)
            entries.append(
                {
                    "file": name,
                    "vendor": book.get("vendor") or Path(name).stem.split("_")[0],
                    "effective_date": book.get("effective_date"),
                }
            )

    for path in sorted(pricebook_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in INDEXABLE and path.name not in seen:
            entries.append(
                {"file": path.name, "vendor": path.stem.split("_")[0], "effective_date": None}
            )
    return entries


def rebuild(pricebook_dir: Path, *, force: bool = False, max_pages: int | None = None) -> dict:
    connection = db.initialise()
    if force:
        for row in connection.execute("SELECT catalog_id FROM catalogs").fetchall():
            registry.delete(connection, row["catalog_id"])

    indexed = skipped = failed = products = 0
    started = time.perf_counter()

    for entry in catalogue_files(pricebook_dir):
        path = pricebook_dir / entry["file"]
        try:
            report = pipeline.index_catalog(
                connection, path, vendor=entry["vendor"],
                effective_date=entry["effective_date"], max_pages=max_pages,
            )
        except pipeline.IndexingError as exc:
            # A book nobody can parse is recorded as failed, with the reason, and
            # the rest of the corpus still indexes. One bad vendor must not leave
            # the estimator with no catalog at all.
            failed += 1
            log.warning("%s: %s", entry["file"], str(exc)[:160])
            continue
        if report.get("skipped"):
            skipped += 1
        else:
            indexed += 1
        products += report.get("products", 0)

    elapsed = time.perf_counter() - started
    integrity = db.integrity_report(connection)
    connection.close()
    return {
        "indexed": indexed, "skipped": skipped, "failed": failed,
        "products": products, "seconds": round(elapsed, 1), "integrity": integrity,
    }


def verify() -> dict:
    connection = db.connect(readonly=True)
    try:
        catalogs = connection.execute(
            "SELECT status, count(*) n, sum(product_count) p FROM catalogs GROUP BY status"
        ).fetchall()
        report = db.integrity_report(connection)
        report["by_status"] = {row["status"]: {"catalogs": row["n"], "products": row["p"]}
                               for row in catalogs}
        return report
    finally:
        connection.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-read every catalog")
    parser.add_argument("--verify", action="store_true", help="report only, change nothing")
    parser.add_argument("--max-pages", type=int, default=None, help="cap pages per book")
    parser.add_argument("--pricebooks", type=Path, default=REPO_ROOT / "pricebooks")
    args = parser.parse_args()

    if args.verify:
        report = verify()
        print(json.dumps(report, indent=2, default=str))
        return 0 if report["ok"] else 1

    report = rebuild(args.pricebooks, force=args.force, max_pages=args.max_pages)
    print(
        f"indexed {report['indexed']}, skipped {report['skipped']}, failed {report['failed']} "
        f"- {report['products']} products in {report['seconds']}s"
    )
    if not report["integrity"]["ok"]:
        print("INTEGRITY PROBLEMS:", report["integrity"]["problems"])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
