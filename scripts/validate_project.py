#!/usr/bin/env python3
"""Pre-flight and extraction checks for the CBC Estimating Copilot.

    python scripts/validate_project.py --all
    python scripts/validate_project.py --check-extraction <project>
    python scripts/validate_project.py --demo

--all runs the pre-flight: reference-library JSON valid, price books present and
not stale, MCP servers importable, hooks present.

--check-extraction validates one project's extracted/*.json against the required
fields. It is also invoked by the post_extraction_validate.py PostToolUse hook,
which warns rather than blocks.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "reference-library"
PRICEBOOKS = ROOT / "pricebooks"
SERVERS = ["pdf-tools", "pricebook", "calc-engine", "artifact-storage", "p21-connector"]
HOOKS = [
    "pre_send_quote.py",
    "pre_delete_guard.py",
    "post_extraction_validate.py",
    "post_quote_format.py",
    "log_audit_trail.py",
]
STALE_DAYS = 180

REQUIRED_REFERENCE = [
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

# Fields whose absence makes an opening unquotable vs merely uncertain.
HARD_FIELDS = ("door_number", "source_page")
SOFT_FIELDS = ("handing", "finish", "fire_rating", "hardware_set")


def _emit(problems: list[str], warnings: list[str]) -> int:
    for warning in warnings:
        print(f"WARN  {warning}")
    for problem in problems:
        print(f"ERROR {problem}")
    if problems:
        print(f"\n{len(problems)} error(s), {len(warnings)} warning(s).")
        return 1
    print(f"\nOK - {len(warnings)} warning(s).")
    return 0


def check_all() -> int:
    problems: list[str] = []
    warnings: list[str] = []

    for relative in REQUIRED_REFERENCE:
        path = REFERENCE / relative
        if not path.exists():
            problems.append(f"missing reference file: {relative}")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"invalid JSON in {relative}: {exc}")
            continue
        if payload.get("status") == "PENDING":
            warnings.append(f"{relative} is PENDING - {payload.get('blocking', 'awaiting CBC input')}")

    index_path = PRICEBOOKS / "index.json"
    if not index_path.exists():
        problems.append("pricebooks/index.json missing - the pricebook server has nothing to search")
    else:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        books = index.get("pricebooks", [])
        if not books:
            problems.append("pricebooks/index.json lists no price books")
        for book in books:
            if not (PRICEBOOKS / book["file"]).exists():
                problems.append(f"price book listed but missing on disk: {book['file']}")
                continue
            effective = book.get("effective_date")
            if not effective:
                warnings.append(f"{book['file']} has no effective date recorded")
                continue
            age = (date.today() - datetime.fromisoformat(effective).date()).days
            if age > STALE_DAYS:
                warnings.append(f"{book['file']} is {age} days old (effective {effective})")

    for name in SERVERS:
        server = ROOT / "mcp-servers" / name / "server.py"
        if not server.exists():
            problems.append(f"MCP server missing: {name}/server.py")
            continue
        result = subprocess.run(
            [sys.executable, str(server), "--selftest"], capture_output=True, text=True
        )
        if result.returncode != 0:
            problems.append(f"MCP server {name} failed selftest: {result.stderr.strip()[:200]}")

    for hook in HOOKS:
        if not (ROOT / ".claude" / "hooks" / hook).exists():
            problems.append(f"guardrail hook missing: {hook}")

    settings = ROOT / ".claude" / "settings.json"
    if not settings.exists():
        problems.append(".claude/settings.json missing")
    else:
        try:
            json.loads(settings.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f".claude/settings.json is not valid JSON: {exc}")

    return _emit(problems, warnings)


def check_extraction(project: str) -> int:
    problems: list[str] = []
    warnings: list[str] = []
    extracted = ROOT / "projects" / project / "extracted"

    if not extracted.exists():
        print(f"WARN  no extracted/ directory for project {project} yet")
        return 0

    schedule_path = extracted / "door_schedule.json"
    if not schedule_path.exists():
        warnings.append(f"{project}: door_schedule.json not written yet")
        return _emit(problems, warnings)

    try:
        payload = json.loads(schedule_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _emit([f"{project}: door_schedule.json is not valid JSON: {exc}"], warnings)

    openings = payload.get("openings", [])
    if not openings:
        problems.append(f"{project}: door_schedule.json contains no openings")

    for opening in openings:
        label = opening.get("door_number") or opening.get("raw_row", "?")[:30]
        for field in HARD_FIELDS:
            if not opening.get(field):
                problems.append(f"{project}: opening {label} is missing {field}")
        if not (opening.get("size") or (opening.get("width") and opening.get("height"))):
            problems.append(f"{project}: opening {label} has no resolvable size")
        if opening.get("confidence") is None:
            problems.append(f"{project}: opening {label} has no confidence score (NFR-2)")
        for field in SOFT_FIELDS:
            if opening.get(field) is None:
                warnings.append(f"{project}: opening {label} is missing {field}")

    frp_path = extracted / "frp_takeoff.json"
    if frp_path.exists():
        frp = json.loads(frp_path.read_text(encoding="utf-8"))
        if frp.get("status") == "PENDING_CONSTANTS":
            warnings.append(f"{project}: FRP quantities blocked - conversion constants pending (Open Item 5)")

    return _emit(problems, warnings)


def _demo() -> None:
    """Runnable check: the extraction validator's field logic."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        project_dir = ROOT / "projects" / "_validate_demo"
        (project_dir / "extracted").mkdir(parents=True, exist_ok=True)
        target = project_dir / "extracted" / "door_schedule.json"
        try:
            target.write_text(
                json.dumps(
                    {
                        "openings": [
                            {
                                "door_number": "01",
                                "size": "3670",
                                "source_page": 14,
                                "confidence": 0.55,
                                "handing": None,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            assert check_extraction("_validate_demo") == 0, "soft-missing fields must warn, not fail"

            target.write_text(
                json.dumps({"openings": [{"size": "3670", "confidence": 0.9}]}), encoding="utf-8"
            )
            assert check_extraction("_validate_demo") == 1, "missing door_number must be an error"
        finally:
            import shutil

            shutil.rmtree(project_dir, ignore_errors=True)
        _ = tmp
    print("validate_project demo OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Run the pre-flight checks")
    parser.add_argument("--check-extraction", metavar="PROJECT")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    if args.demo:
        _demo()
        return 0
    if args.check_extraction:
        return check_extraction(args.check_extraction)
    return check_all()


if __name__ == "__main__":
    sys.exit(main())
