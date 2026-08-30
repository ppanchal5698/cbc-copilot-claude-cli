#!/usr/bin/env python3
"""Measure the catalog search index.

    python scripts/bench_catalog.py                 # search latency
    python scripts/bench_catalog.py --concurrent    # searches during an index
    python scripts/bench_catalog.py --all

The baseline is what this replaced: the pricebook MCP server opened every PDF and
ran difflib over every line of every page, on every query.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog_index import db, registry, search  # noqa: E402
from catalog_index.models import ProductRecord  # noqa: E402

# Measured on this corpus (18 PDFs, 1 391 pages) before the index existed.
BASELINE_COLD_MS = 6020.0
BASELINE_WARM_MS = 2510.0

QUERIES = [
    "hinge", "stainless steel grab bar", "B-2888", "150CX18", "door lock",
    "heavy duty hinge", "paper towel dispenser", "threshold", "3510",
    "exit device", "FRP", "BB1279", "soap dispenser", "US26D",
]


def _percentiles(samples: list[float]) -> dict[str, float]:
    samples = sorted(samples)
    at = lambda q: samples[min(len(samples) - 1, int(len(samples) * q))]  # noqa: E731
    return {
        "p50": round(at(0.50), 2), "p95": round(at(0.95), 2),
        "p99": round(at(0.99), 2), "max": round(samples[-1], 2),
    }


def bench_search(rounds: int = 100) -> int:
    connection = db.connect(readonly=True)
    try:
        products = connection.execute("SELECT count(*) FROM products").fetchone()[0]
        catalogs = connection.execute(
            "SELECT count(*) FROM catalogs WHERE status='ready'"
        ).fetchone()[0]
        print(f"index: {products} products across {catalogs} ready catalogs\n")

        exact, full_text, everything = [], [], []
        for query in QUERIES:
            samples = []
            for _ in range(rounds):
                started = time.perf_counter()
                result = search.search(connection, query, limit=10)
                samples.append((time.perf_counter() - started) * 1000)
            everything += samples
            (exact if len(query.split()) == 1 and any(c.isdigit() for c in query)
             else full_text).extend(samples)
            print(f"  {query:<26} {statistics.median(samples):6.2f} ms  "
                  f"{result['total_matched']:>3} matched")

        print()
        for label, samples in (("exact identifier", exact), ("full text", full_text),
                               ("all queries", everything)):
            if samples:
                stats = _percentiles(samples)
                print(f"  {label:<18} p50 {stats['p50']:6.2f} | p95 {stats['p95']:6.2f} "
                      f"| p99 {stats['p99']:6.2f} | max {stats['max']:6.2f} ms")

        overall = _percentiles(everything)
        print(f"\n  versus the PDF scan it replaced: {BASELINE_COLD_MS:.0f} ms cold, "
              f"{BASELINE_WARM_MS:.0f} ms warm")
        print(f"  speed-up at p50: {BASELINE_WARM_MS / max(overall['p50'], 0.01):,.0f}x warm, "
              f"{BASELINE_COLD_MS / max(overall['p50'], 0.01):,.0f}x cold")
        return 0
    finally:
        connection.close()


def bench_concurrent(seconds: int = 5) -> int:
    """Search latency while a catalog is being indexed and swapped underneath it."""
    path = db.index_path()
    stop = threading.Event()
    samples: list[float] = []
    errors: list[str] = []

    def reader() -> None:
        connection = db.connect(path, readonly=True)
        try:
            while not stop.is_set():
                started = time.perf_counter()
                try:
                    search.search(connection, "stainless steel", limit=10)
                except Exception as exc:
                    errors.append(repr(exc))
                samples.append((time.perf_counter() - started) * 1000)
        finally:
            connection.close()

    threads = [threading.Thread(target=reader, daemon=True) for _ in range(4)]
    for thread in threads:
        thread.start()

    writer = db.connect(path, readonly=False)
    swaps = 0
    try:
        catalog_id, _ = registry.register(
            writer, vendor="_bench", file_name="_bench.pdf", hash_hex="v1")
        deadline = time.time() + seconds
        while time.time() < deadline:
            records = [
                ProductRecord("_bench", (n % 40) + 1, f"BN{n:05d}", f"bench part {n}",
                              "stainless steel assembly", "bench", 1.0 + n, "EA")
                for n in range(2000)
            ]
            build, _ = registry.stage(writer, catalog_id, records, version=1)
            registry.activate(writer, catalog_id, build, extractor="bench")
            swaps += 1
        registry.delete(writer, catalog_id)
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=5)
        writer.close()

    stats = _percentiles(samples)
    print(f"4 readers, {len(samples)} searches during {swaps} index swaps of 2 000 rows")
    print(f"  p50 {stats['p50']:.2f} | p95 {stats['p95']:.2f} | p99 {stats['p99']:.2f} "
          f"| max {stats['max']:.2f} ms")
    print(f"  errors: {len(errors)}" + (f" - {errors[:2]}" if errors else " (no SQLITE_BUSY)"))
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrent", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--rounds", type=int, default=100)
    args = parser.parse_args()

    if not db.index_path().exists():
        print(f"no index at {db.index_path()} - run `python -m catalog_index.rebuild`")
        return 1

    status = 0
    if args.concurrent or args.all:
        status |= bench_concurrent()
        print()
    if not args.concurrent or args.all:
        status |= bench_search(args.rounds)
    return status


if __name__ == "__main__":
    sys.exit(main())
