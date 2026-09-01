"""What a run must have written before its output is accepted.

These checks were in `scripts/validate_project.py`, which made the worker import
a script to find out whether a job had produced valid artifacts - `apps` reaching
sideways into `scripts/` for a rule that is neither a script's business nor the
application's. The rule is about the domain's own files, so it lives in the
domain, and `scripts/validate_project.py` is the command-line front for it.

`check_extraction`, `check_pricing` and `check_proposal` each return
`(problems, warnings)`. Problems reject the job; warnings are reported and let it
through. `validate_job_artifacts` is the worker's gate and raises on problems.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import fitz

from cbc.core.paths import repo_root
from cbc.core.pdfrows import rows_from_words

ROOT = repo_root()

HARD_FIELDS = ("door_number", "source_page")
SOFT_FIELDS = ("handing", "finish", "fire_rating", "hardware_set")

PRICING_LINE_FIELDS = ("line_id", "group", "group_type", "quantity", "cost_source")
PRICING_GROUP_TYPES = frozenset({"door", "accessories", "frp", "other"})


# A citation that names a sheet somebody can open, rather than a vendor's name.
# "Price based on Pemko catalog" is not a citation; "pemko_markar_price_book_2026.pdf
# PDF p67" is - and it is exactly what find_pages hands back.
_CATALOG_FILE = re.compile(r"[\w.-]+\.(?:pdf|xlsx|xls)", re.IGNORECASE)

# The only two cost paths a run can walk on its own: P21 answered, or the figure
# was read off a catalog page. Everything else in the CBC cost-source vocabulary
# describes a human doing something.
_COST_SOURCES_A_RUN_CAN_READ = frozenset({"P21_LAST_PO", "LIST_X_MULTIPLIER"})

_CLAIMS_APPROVAL = re.compile(r"(?:estimator|purchasing)[- ]?approved", re.IGNORECASE)
def _added_by_hand(row: dict) -> bool:
    """Did the estimator enter this line themselves, rather than a drawing produce it?

    The UI writes both markers when someone adds a line; either one is enough.
    """
    return bool(row.get("added_by_hand")) or str(row.get("status") or "").lower() == "by_hand"
def _valid_bbox(box: Any) -> bool:
    return (
        isinstance(box, list)
        and len(box) == 4
        and all(isinstance(v, (int, float)) for v in box)
        and box[2] > box[0]
        and box[3] > box[1]
    )


# How much of a claimed box has to sit on text the extractor actually found.
# Measured on a real fabrication: six invented boxes scored 0.001-0.179 against
# page 19 of the Baldwin set, while every real row and every real cell scores
# 1.000. Half is a wide margin either way.
BBOX_COVERAGE = 0.5
def _page_boxes(pdf_path: Path, page_number: int) -> tuple[list, tuple[float, float]] | None:
    """Every row and cell box the extractor finds on one page, in display space."""
    # Imported at module scope. These used to be imported here inside a bare
    # `except Exception: return None`, together with a sys.path hack needed only
    # while this code lived in scripts/ - so any import problem disabled the
    # whole bbox check and reported a clean pass. It is a hard dependency; if it
    # cannot be imported the run should say so, not quietly stop checking.
    try:
        document = fitz.open(pdf_path)
    except Exception:
        return None
    try:
        if not 0 <= page_number - 1 < document.page_count:
            return None
        page = document[page_number - 1]
        boxes = []
        for row in rows_from_words(page):
            boxes.append(fitz.Rect(row["bbox"]))
            boxes.extend(fitz.Rect(cell) for cell in row["cell_boxes"])
        return boxes, (page.rect.width, page.rect.height)
    finally:
        document.close()
def check_bboxes_are_real(project: str, openings: list[dict]) -> tuple[list[str], list[str]]:
    """Every bbox must land on text that is genuinely there.

    The estimator verifies extracted values by eye against a highlight on the
    real sheet, so a bbox is not decoration - it is the check itself. A run
    produced six boxes of identical width marching down the page in exact
    20-point steps: an arithmetic sequence, invented to satisfy a rule that only
    asked whether a bbox was well formed. Shape is not truth, and in a drawing
    as dense as a plan set an invented box still overlaps *something*, so
    "contains a word" does not separate them either.

    What does: a real box is one the extractor could have produced. Compare each
    claim against the rows and cells actually on that page.
    """
    problems: list[str] = []
    warnings: list[str] = []

    raw = ROOT / "projects" / project / "uploads" / "raw"
    pdfs = sorted(raw.glob("*.pdf")) if raw.is_dir() else []

    cache: dict[tuple[str, int], Any] = {}
    for index, opening in enumerate(openings, start=1):
        label = opening.get("door_number") or opening.get("mark") or f"opening {index}"
        box = opening.get("bbox")
        page_number = opening.get("source_page")
        if not _valid_bbox(box) or not isinstance(page_number, int):
            continue  # already reported by the shape checks

        named = opening.get("source_file")
        candidates = [p for p in pdfs if named and Path(named).name == p.name] or pdfs
        if len(candidates) != 1:
            warnings.append(
                f"{project}: opening {label} cannot be checked against its sheet - "
                f"{'no source_file and ' if not named else ''}"
                f"{len(pdfs)} PDF(s) in uploads/raw"
            )
            continue
        pdf = candidates[0]

        key = (pdf.name, page_number)
        if key not in cache:
            cache[key] = _page_boxes(pdf, page_number)
        found = cache[key]
        if found is None:
            warnings.append(f"{project}: could not read {pdf.name} page {page_number} to check bboxes")
            continue
        boxes, (width, height) = found

        size = opening.get("page_size") or {}
        if isinstance(size, dict) and size.get("width") and size.get("height"):
            if abs(size["width"] - width) > 1 or abs(size["height"] - height) > 1:
                problems.append(
                    f"{project}: opening {label} records page_size "
                    f"{size['width']}x{size['height']} but page {page_number} of "
                    f"{pdf.name} is {width:g}x{height:g}. A bbox scaled against the "
                    "wrong frame lands nowhere near its row"
                )

        import fitz

        claim = fitz.Rect(box)
        area = claim.get_area()
        covered = max(
            ((claim & other).get_area() / area if area else 0.0) for other in boxes
        ) if boxes and area else 0.0
        if covered < BBOX_COVERAGE:
            problems.append(
                f"{project}: opening {label} bbox {box} does not sit on any text "
                f"found on page {page_number} (covers {covered:.0%}). It was not "
                "measured - take it from the extractor's row, do not construct one"
            )
    return problems, warnings
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

    # Take the same shapes the importer takes, and no fewer. This gate runs
    # first, so anything it refuses never reaches sync - and it was refusing a
    # bare array that `_normalize_schedule_payload` has always accepted, and a
    # `lines` wrapper that a run produced with every opening intact. A gate
    # stricter than the thing it guards fails work that would have imported
    # cleanly. What each opening must contain is checked below, unchanged.
    if isinstance(payload, list):
        openings = payload
    elif isinstance(payload, dict):
        openings = payload.get("openings")
        if not openings and isinstance(payload.get("lines"), list):
            openings = payload["lines"]
        openings = openings or []
    else:
        problems.append(f"{project}: door_schedule.json must be a JSON object or an array")
        return problems, warnings
    if not openings:
        problems.append(f"{project}: door_schedule.json contains no openings")

    for opening in openings:
        opening = _normalize_opening(opening)
        label = opening.get("door_number") or opening.get("description") or "?"
        if opening.get("hw_set") and not opening.get("hardware_set"):
            warnings.append(f"{project}: opening {label} uses hw_set; prefer hardware_set")

        # A line the estimator added by hand was never read off a drawing, so it has
        # no page, no bbox and no door number - a hand dryer nobody drew is still a
        # line on the quote. Every one of those checks fired on it, reporting five
        # problems against a healthy project, and the same demand one layer down
        # made a pricing pass invent a page number to satisfy it (NFR-2).
        #
        # What still applies is the part that is about the estimator's own entry:
        # it needs something to identify it, and a confidence score.
        if _added_by_hand(opening):
            if not (opening.get("description") or opening.get("door_number")):
                problems.append(
                    f"{project}: hand-added opening has neither a door_number nor a "
                    "description - nothing identifies it on the quote"
                )
            if opening.get("confidence") is None:
                problems.append(
                    f"{project}: hand-added opening {label} has no confidence score (NFR-2)"
                )
            continue

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

    # Shape is checked above; this checks the numbers are real. It opens the
    # sheet, so it runs once per page rather than once per opening.
    box_problems, box_warnings = check_bboxes_are_real(project, openings)
    problems.extend(box_problems)
    warnings.extend(box_warnings)

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

    # Either shape. A run writes a bare array about as often as the wrapped
    # object it is asked for, and rejecting the array here returned before a
    # single pricing rule ran - so the shape decided whether the checks happened.
    lines = payload if isinstance(payload, list) else (
        payload.get("lines") if isinstance(payload, dict) else None
    )
    if not isinstance(lines, list) or not lines:
        problems.append(f"{project}: priced/line_items.json must contain a non-empty lines array")
        return problems, warnings

    priced_count = 0
    for index, line in enumerate(lines, start=1):
        label = line.get("line_id") or line.get("description", f"line {index}")[:40]
        for field in PRICING_LINE_FIELDS:
            if line.get(field) is None or line.get(field) == "":
                problems.append(f"{project}: priced line {label} is missing {field}")

        # A line has to say what it is. The matcher records the specified item -
        # "IVES 700 83\", 630" - and a run that dropped it wrote 25 blank MANUAL
        # rows: not wrong, but useless to the estimator who has to price them.
        if not (line.get("part_number") or line.get("description")):
            problems.append(
                f"{project}: priced line {label} has neither part_number nor description "
                "- carry the specified item across from hardware_sets.json"
            )
        # NFR-3: an unauditable line is not a line - but "auditable" is not the same
        # question for every line.
        #
        # A door or an FRP run comes off a drawing, so it has a page and must name
        # it. An accessory often does not: the estimator adds a hand dryer nobody
        # drew, and there is no page to point at. Demanding one anyway rejected a
        # correctly priced hand-added accessory and took the whole quote with it -
        # and on the retry the pass satisfied the rule by *inventing* a page,
        # putting the hand dryer on the door-schedule sheet. A check that makes
        # fabrication the cheapest way out is worse than the gap it was closing
        # (NFR-2).
        #
        # So the accessory must still be traceable, by the half of NFR-3 that
        # applies to it: where its price came from.
        from_a_drawing = line.get("group_type") in ("door", "frp")
        if line.get("source_page") is None:
            if from_a_drawing:
                problems.append(f"{project}: priced line {label} has no source_page")
            elif not str(line.get("cost_source_detail") or "").strip():
                problems.append(
                    f"{project}: line {label} has neither a source_page nor a "
                    "cost_source_detail - a line off the drawings must name its page, "
                    "and one added by hand must name where its price came from (NFR-3)"
                )
        # NFR-2: a manual line is an instruction to a human, so it says why.
        if line.get("cost_source") == "MANUAL" and not str(
            line.get("cost_source_detail") or line.get("reason") or ""
        ).strip():
            problems.append(
                f"{project}: MANUAL line {label} records no reason - say why it "
                "cannot be priced automatically"
            )

        # A line has to say what it is. An autopilot run wrote ten lines whose
        # part_number was null and whose whole identity was "Manual entry
        # required - wood door" - technically honest, and useless: an estimator
        # cannot price an item the quote does not name. Carrying the specified
        # part across from hardware_sets.json is the pass's job even, and
        # especially, when nothing matched (NFR-2).
        if not (line.get("part_number") or "").strip() and not (
            line.get("description") or ""
        ).strip():
            problems.append(
                f"{project}: line {label} names neither a part_number nor a "
                "description - nothing on it tells an estimator what to price. "
                "Copy the specified item across even when no match was found"
            )

        # A cost a run writes must come from somewhere a run can actually read.
        #
        # Only two sources qualify: P21 returned a last-PO price, or a figure was
        # read off a catalog page. DISTRIBUTOR_MANUAL, VENDOR_RFQ and MANUAL all
        # mean *a person supplied this number* - there is no distributor on the
        # phone during a pipeline run and no RFQ has been answered - so from a run
        # they carry no cost.
        #
        # This started as a narrower rule that named MANUAL alone. The next run
        # relabelled 34 invented costs as DISTRIBUTOR_MANUAL and passed. Naming
        # one label taught the pass which label to avoid, so the rule now names
        # what a run may legitimately obtain instead (NFR-2).
        if (
            line.get("cost") is not None
            and line.get("cost_source") not in _COST_SOURCES_A_RUN_CAN_READ
            and not _added_by_hand(line)
        ):
            problems.append(
                f"{project}: line {label} is {line.get('cost_source')} and carries a "
                f"cost of {line['cost']}. That source means a person supplied the "
                "number, and no person did. Leave cost null and say what the "
                "estimator needs to look up"
            )

        # And it may not claim someone signed off on it.
        #
        # Every one of those 34 lines read "Estimator approved cost: ...". No
        # estimator had seen the quote. An invented number is a gap; an invented
        # number wearing a human's approval is a gap nobody will look for (NFR-1).
        detail_text = str(line.get("cost_source_detail") or "")
        if not _added_by_hand(line) and _CLAIMS_APPROVAL.search(detail_text):
            problems.append(
                f"{project}: line {label} says {detail_text[:52]!r}. A run cannot "
                "record an approval on the estimator's behalf - that is the one "
                "thing it is not allowed to do"
            )

        # A computed cost has to name the sheet it was read from.
        #
        # The same run put three different costs on one part number and cited
        # `source_page: 14` for all of them - the bid set's door-schedule page,
        # not a price book. `cost_source_detail` said "Price based on Pemko
        # catalog", which names no page anyone can open. The catalog tools hand
        # back a file name and a locator precisely so this citation is available
        # (NFR-3).
        if line.get("cost_source") == "LIST_X_MULTIPLIER":
            detail = str(line.get("cost_source_detail") or "")
            if not _CATALOG_FILE.search(detail):
                problems.append(
                    f"{project}: line {label} claims list x multiplier but its "
                    f"cost_source_detail ({detail[:48]!r}) names no price-book file. "
                    "Quote the file_path and locator find_pages returned, so the "
                    "number can be checked against the page it came from"
                )
        if line.get("cost") is not None:
            priced_count += 1
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

    # Not errors: an all-Allegion bid legitimately prices nothing automatically
    # (CLAUDE.md - bought via Banner or SecLock, so manual entry). The point is
    # that the quote says so rather than looking finished.
    if priced_count == 0:
        warnings.append(
            f"{project}: not one of {len(lines)} line(s) carries a price - this quote "
            "is entirely manual and is not ready to send to anyone"
        )

    hw_path = root / "extracted" / "hardware_sets.json"
    if hw_path.exists():
        try:
            groups = json.loads(hw_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            groups = []
        specified = {
            str(entry.get("hardware_set"))
            for entry in (groups if isinstance(groups, list) else [])
            if entry.get("hardware_set")
        }
        quoted = {str(line.get("group")) for line in lines if line.get("group")}
        for missing in sorted(specified - quoted):
            warnings.append(
                f"{project}: hardware {missing} was extracted but has no line on the quote"
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


# Which checks each job type has to pass before its output reaches MongoDB.
#
# A dict rather than an if/elif chain because the chain ended in `else: return`,
# and a job type nobody remembered to add fell through it silently. That is
# exactly what happened to `run_full_pipeline`: the one path with no human
# checkpoints was also the one path with no artifact checks. GATED_JOB_TYPES
# below asserts the mapping stays complete.
ARTIFACT_CHECKS: dict[str, tuple] = {
    "extract_bid_set": (lambda slug: check_extraction(slug, require_scope=True),),
    "rerun_extraction": (lambda slug: check_extraction(slug, require_scope=False),),
    "match_and_price": (lambda slug: check_pricing(slug, require_hardware_sets=True),),
    "build_proposal": (check_proposal,),
    # One session produced all three, so all three are checked.
    "run_full_pipeline": (
        lambda slug: check_extraction(slug, require_scope=True),
        lambda slug: check_pricing(slug, require_hardware_sets=True),
        check_proposal,
    ),
}
UNCHECKED_JOB_TYPES = frozenset(
    {"ingest_pricebook", "ingest_addendum", "index_catalog", "delete_catalog"}
)
def validate_job_artifacts(job_type: str, project_slug: str) -> None:
    """Raise ValueError if job artifacts fail validation (worker gate)."""
    problems: list[str] = []
    warnings: list[str] = []

    checks = ARTIFACT_CHECKS.get(job_type)
    if checks is None:
        if job_type not in UNCHECKED_JOB_TYPES:
            # Better a loud failure than a job quietly skipping its own gate.
            raise ValueError(
                f"job type {job_type!r} has no entry in ARTIFACT_CHECKS and is not "
                "listed as unchecked - add it to one or the other"
            )
        return

    for check in checks:
        p, w = check(project_slug)
        problems.extend(p)
        warnings.extend(w)

    for warning in warnings:
        print(f"WARN  {warning}", file=sys.stderr)

    if problems:
        detail = "; ".join(problems[:5])
        if len(problems) > 5:
            detail += f" (+{len(problems) - 5} more)"
        raise ValueError(f"artifact validation failed: {detail}")
