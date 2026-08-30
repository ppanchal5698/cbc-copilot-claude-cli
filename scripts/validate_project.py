#!/usr/bin/env python3
"""Pre-flight and artifact checks for the CBC Estimating Copilot.

    python scripts/validate_project.py --all
    python scripts/validate_project.py --check-extraction <project>
    python scripts/validate_project.py --check-pricing <project>
    python scripts/validate_project.py --check-proposal <project>
    python scripts/validate_project.py --demo

--all runs the pre-flight: reference-library JSON valid, price books present and
not stale, MCP servers importable, hooks present.

--check-extraction validates one project's extracted/*.json against the required
fields. It is also invoked by the post_extraction_validate.py PostToolUse hook,
which warns rather than blocks. The worker calls validate_job_artifacts() before
sync and fails the job on errors.
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

PRICING_LINE_FIELDS = ("line_id", "group", "group_type", "quantity", "cost_source")
PRICING_GROUP_TYPES = frozenset({"door", "accessories", "frp", "other"})


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


def _valid_bbox(box: Any) -> bool:
    return (
        isinstance(box, list)
        and len(box) == 4
        and all(isinstance(v, (int, float)) for v in box)
        and box[2] > box[0]
        and box[3] > box[1]
    )


def _valid_page_size(page_size: Any) -> bool:
    if not isinstance(page_size, dict):
        return False
    width, height = page_size.get("width"), page_size.get("height")
    return isinstance(width, (int, float)) and isinstance(height, (int, float)) and width > 0 and height > 0


def _normalize_opening(opening: dict[str, Any]) -> dict[str, Any]:
    """Apply field aliases in place for validation."""
    if opening.get("hardware_set") is None and opening.get("hw_set") is not None:
        opening["hardware_set"] = opening["hw_set"]
    if opening.get("door_number") is None and opening.get("mark"):
        opening["door_number"] = opening["mark"]
    return opening


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


def check_extraction(project: str, *, require_scope: bool = False) -> tuple[list[str], list[str]]:
    """Return (problems, warnings) for extraction artifacts."""
    problems: list[str] = []
    warnings: list[str] = []
    extracted = ROOT / "projects" / project / "extracted"

    if not extracted.exists():
        problems.append(f"{project}: no extracted/ directory")
        return problems, warnings

    if require_scope:
        for name in ("scope_metadata.json", "scope_summary.json"):
            if not (extracted / name).exists():
                problems.append(f"{project}: missing extracted/{name}")

    schedule_path = extracted / "door_schedule.json"
    if not schedule_path.exists():
        problems.append(f"{project}: door_schedule.json not written")
        return problems, warnings

    try:
        payload = json.loads(schedule_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        problems.append(f"{project}: door_schedule.json is not valid JSON: {exc}")
        return problems, warnings

    if isinstance(payload, list):
        problems.append(
            f"{project}: door_schedule.json must be {{\"openings\": [...]}}, not a bare array"
        )
        return problems, warnings

    if not isinstance(payload, dict):
        problems.append(f"{project}: door_schedule.json must be a JSON object")
        return problems, warnings

    openings = payload.get("openings", [])
    if not openings:
        problems.append(f"{project}: door_schedule.json contains no openings")

    for opening in openings:
        opening = _normalize_opening(opening)
        label = opening.get("door_number") or opening.get("raw_row", "?")[:30]
        if opening.get("hw_set") and not opening.get("hardware_set"):
            warnings.append(f"{project}: opening {label} uses hw_set; prefer hardware_set")
        for field in HARD_FIELDS:
            if not opening.get(field):
                problems.append(f"{project}: opening {label} is missing {field}")
        if not (opening.get("size") or (opening.get("width") and opening.get("height"))):
            problems.append(f"{project}: opening {label} has no resolvable size")
        if opening.get("confidence") is None:
            problems.append(f"{project}: opening {label} has no confidence score (NFR-2)")
        if not _valid_bbox(opening.get("bbox")):
            problems.append(f"{project}: opening {label} has no valid bbox (NFR-3)")
        if not _valid_page_size(opening.get("page_size")):
            problems.append(f"{project}: opening {label} has no valid page_size (NFR-3)")
        for field in SOFT_FIELDS:
            if opening.get(field) is None:
                warnings.append(f"{project}: opening {label} is missing {field}")

    frp_path = extracted / "frp_takeoff.json"
    if frp_path.exists():
        frp = json.loads(frp_path.read_text(encoding="utf-8"))
        if frp.get("status") == "PENDING_CONSTANTS":
            warnings.append(f"{project}: FRP quantities blocked - conversion constants pending (Open Item 5)")

    return problems, warnings


def check_pricing(project: str, *, require_hardware_sets: bool = False) -> tuple[list[str], list[str]]:
    """Return (problems, warnings) for priced artifacts."""
    problems: list[str] = []
    warnings: list[str] = []
    root = ROOT / "projects" / project

    if require_hardware_sets:
        hw_path = root / "extracted" / "hardware_sets.json"
        if not hw_path.exists():
            problems.append(f"{project}: missing extracted/hardware_sets.json")

    priced_path = root / "priced" / "line_items.json"
    if not priced_path.exists():
        problems.append(f"{project}: priced/line_items.json not written")
        return problems, warnings

    try:
        payload = json.loads(priced_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        problems.append(f"{project}: priced/line_items.json is not valid JSON: {exc}")
        return problems, warnings

    if not isinstance(payload, dict):
        problems.append(f"{project}: priced/line_items.json must be a JSON object")
        return problems, warnings

    lines = payload.get("lines")
    if not isinstance(lines, list) or not lines:
        problems.append(f"{project}: priced/line_items.json must contain a non-empty lines array")
        return problems, warnings

    for index, line in enumerate(lines, start=1):
        label = line.get("line_id") or line.get("description", f"line {index}")[:40]
        for field in PRICING_LINE_FIELDS:
            if line.get(field) is None or line.get(field) == "":
                problems.append(f"{project}: priced line {label} is missing {field}")
        group_type = line.get("group_type")
        if group_type and group_type not in PRICING_GROUP_TYPES:
            warnings.append(f"{project}: priced line {label} has unusual group_type {group_type!r}")
        cost = line.get("cost")
        if cost is not None:
            try:
                parsed = float(cost)
            except (TypeError, ValueError):
                problems.append(f"{project}: priced line {label} has unreadable cost")
            else:
                if parsed < 0:
                    problems.append(f"{project}: priced line {label} has negative cost")
                elif line.get("sale_ea") is None or line.get("ext_price") is None:
                    problems.append(
                        f"{project}: priced line {label} has cost but missing sale_ea or ext_price"
                    )

    return problems, warnings


def check_proposal(project: str) -> tuple[list[str], list[str]]:
    """Return (problems, warnings) for proposal artifacts."""
    problems: list[str] = []
    warnings: list[str] = []
    root = ROOT / "projects" / project

    if not (root / "quotation.html").exists():
        problems.append(f"{project}: quotation.html not written")
    if not (root / "review" / "review_flags.json").exists():
        problems.append(f"{project}: review/review_flags.json not written")
    if not (root / "review" / "review_summary.html").exists():
        warnings.append(f"{project}: review/review_summary.html not written")
    if not (root / "review" / "quotation_email_draft.md").exists():
        warnings.append(f"{project}: review/quotation_email_draft.md not written")

    return problems, warnings


def validate_job_artifacts(job_type: str, project_slug: str) -> None:
    """Raise ValueError if job artifacts fail validation (worker gate)."""
    problems: list[str] = []
    warnings: list[str] = []

    if job_type in ("extract_bid_set", "rerun_extraction"):
        p, w = check_extraction(project_slug, require_scope=job_type == "extract_bid_set")
        problems.extend(p)
        warnings.extend(w)
    elif job_type == "match_and_price":
        p, w = check_pricing(project_slug, require_hardware_sets=True)
        problems.extend(p)
        warnings.extend(w)
    elif job_type == "build_proposal":
        p, w = check_proposal(project_slug)
        problems.extend(p)
        warnings.extend(w)
    else:
        return

    for warning in warnings:
        print(f"WARN  {warning}", file=sys.stderr)

    if problems:
        detail = "; ".join(problems[:5])
        if len(problems) > 5:
            detail += f" (+{len(problems) - 5} more)"
        raise ValueError(f"artifact validation failed: {detail}")


def _demo() -> None:
    """Runnable check: the extraction validator's field logic."""
    import shutil

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
                            "bbox": [10, 20, 100, 40],
                            "page_size": {"width": 2592, "height": 1728},
                            "handing": None,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        problems, warnings = check_extraction("_validate_demo")
        assert not problems, problems
        assert warnings, "soft-missing fields must warn"

        target.write_text(
            json.dumps({"openings": [{"size": "3670", "confidence": 0.9}]}), encoding="utf-8"
        )
        problems, _ = check_extraction("_validate_demo")
        assert problems, "missing door_number must be an error"

        target.write_text(json.dumps([{"door_number": "01"}]), encoding="utf-8")
        problems, _ = check_extraction("_validate_demo")
        assert any("bare array" in p for p in problems)
    finally:
        shutil.rmtree(project_dir, ignore_errors=True)
    print("validate_project demo OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Run the pre-flight checks")
    parser.add_argument("--check-extraction", metavar="PROJECT")
    parser.add_argument("--check-pricing", metavar="PROJECT")
    parser.add_argument("--check-proposal", metavar="PROJECT")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    if args.demo:
        _demo()
        return 0
    if args.check_extraction:
        problems, warnings = check_extraction(args.check_extraction)
        return _emit(problems, warnings)
    if args.check_pricing:
        problems, warnings = check_pricing(args.check_pricing, require_hardware_sets=True)
        return _emit(problems, warnings)
    if args.check_proposal:
        problems, warnings = check_proposal(args.check_proposal)
        return _emit(problems, warnings)
    return check_all()


if __name__ == "__main__":
    sys.exit(main())
