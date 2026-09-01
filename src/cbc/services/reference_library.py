"""Read/write helpers for curated reference-library files on disk."""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from cbc.core.paths import repo_root

ROOT = repo_root()
TIERS_FILE = ROOT / "reference-library" / "multipliers" / "vendor_tiers.json"
HARDWARE_SETS = ROOT / "reference-library" / "hardware_sets"
MARGINS_FILE = ROOT / "reference-library" / "margins" / "margin_framework.json"
TAX_FILE = ROOT / "reference-library" / "tax" / "sales_tax_rates.json"
ADDERS_FILE = ROOT / "reference-library" / "adders" / "manual_adders.json"
SPECIAL_MARGINS_FILE = ROOT / "reference-library" / "multipliers" / "special_customer_margins.json"
FINISHES_FILE = ROOT / "reference-library" / "finishes" / "finish_crosswalk.json"
FRAME_DEPTHS_FILE = ROOT / "reference-library" / "frame_depths" / "wall_type_to_depth.json"
FRP_CONSTANTS_FILE = ROOT / "reference-library" / "frp_constants" / "conversion_constants.json"

# The constants the FRP take-off needs before it can convert geometry to quantities.
# opening_handling is guidance, not arithmetic, so it does not gate the status.
FRP_REQUIRED_CONSTANTS = (
    "panel_size",
    "waste_pct",
    "trim_stick_length",
    "adhesive_coverage_sqft_per_unit",
)
FRP_NUMERIC_CONSTANTS = ("waste_pct", "trim_stick_length", "adhesive_coverage_sqft_per_unit")
FRP_EDITABLE_CONSTANTS = FRP_REQUIRED_CONSTANTS + ("opening_handling",)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON through a temp file + os.replace.

    cbc_core.calc.bands() re-reads margin_framework.json whenever its mtime moves;
    a plain truncate-and-write can be read half-finished at exactly that moment.
    Replacing the file in one step means a reader sees the old bytes or the new,
    never a torn document.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2) + "\n")
        os.replace(tmp, path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_margins() -> dict[str, Any]:
    """The full margin framework document, structure preserved."""
    return json.loads(MARGINS_FILE.read_text(encoding="utf-8"))


def update_margins(
    bands: dict[str, float] | None = None,
    accessories: float | None = None,
) -> dict[str, Any]:
    """Edit the margin framework in place and return the updated document.

    The JSON file is the source of truth the pricing pass reads, so this is a
    deliberate, human-initiated edit (file-safety rule) - the same shape as
    sync_vendor_categories above. Only the margin and its divisor are touched per
    band; every other field the file carries is left as written.
    """
    payload = load_margins()
    known = {b.get("key") for b in payload.get("bands", []) if b.get("key")}

    if bands:
        unknown = set(bands) - known
        if unknown:
            raise ValueError(f"unknown margin band(s): {', '.join(sorted(unknown))}")
        for record in payload.get("bands", []):
            key = record.get("key")
            if key in bands:
                margin = float(bands[key])
                if not 0 <= margin < 1:
                    raise ValueError(f"margin for {key!r} must be in [0, 1), got {margin}")
                record["margin"] = margin
                record["divisor"] = round(1 - margin, 4)

    if accessories is not None:
        accessories = float(accessories)
        if not 0 <= accessories < 1:
            raise ValueError(f"accessories margin must be in [0, 1), got {accessories}")
        payload["accessories_derived"] = accessories

    _atomic_write_json(MARGINS_FILE, payload)
    return payload


def load_tax_rates() -> dict[str, Any]:
    """The full sales-tax document, structure preserved."""
    return json.loads(TAX_FILE.read_text(encoding="utf-8"))


def update_tax_rates(
    rates: dict[str, float] | None = None,
    remove: list[str] | None = None,
) -> dict[str, Any]:
    """Upsert nexus tax rates and/or drop jurisdictions, returning the updated doc.

    Like the margin edit, the JSON file is the source of truth cbc_core.calc reads,
    so this is the deliberate human-initiated write the file-safety rule allows.
    A dropped jurisdiction means CBC no longer has nexus there - the state then
    resolves to a 0% rate, exactly as any state absent from the table does.
    """
    payload = load_tax_rates()
    table = dict(payload.get("rates", {}))

    if rates:
        for code, rate in rates.items():
            rate = float(rate)
            if not 0 <= rate < 1:
                raise ValueError(f"tax rate for {code!r} must be in [0, 1), got {rate}")
            table[code.strip().upper()] = rate

    for code in remove or []:
        table.pop(code.strip().upper(), None)

    payload["rates"] = table
    _atomic_write_json(TAX_FILE, payload)
    return payload


def load_adders() -> dict[str, Any]:
    """The full manual-adders document, structure preserved."""
    return json.loads(ADDERS_FILE.read_text(encoding="utf-8"))


def update_hager_adders(
    items: dict[str, float] | None = None,
    remove: list[str] | None = None,
) -> dict[str, Any]:
    """Upsert or drop Hager list adders and return the updated document.

    These are LIST dollar amounts (not fractions) - the pricing pass multiplies
    each by the base item's category multiplier. Keying on the adder name keeps a
    value edit from touching any other row.
    """
    payload = load_adders()
    block = payload.setdefault("hager_list_adders", {})
    rows = list(block.get("items", []))
    by_name = {str(r.get("name")): r for r in rows}

    if items:
        for raw_name, value in items.items():
            name = raw_name.strip()
            if not name:
                raise ValueError("adder name must not be blank")
            value = float(value)
            if value < 0:
                raise ValueError(f"adder {name!r} must not be negative, got {value}")
            if name in by_name:
                by_name[name]["list_adder"] = value
            else:
                row = {"name": name, "list_adder": value}
                rows.append(row)
                by_name[name] = row

    if remove:
        drop = {r.strip() for r in remove}
        rows = [r for r in rows if str(r.get("name")) not in drop]

    block["items"] = rows
    payload["hager_list_adders"] = block
    _atomic_write_json(ADDERS_FILE, payload)
    return payload


def load_special_margins() -> dict[str, Any]:
    """The full special-customer-margins document, structure preserved."""
    return json.loads(SPECIAL_MARGINS_FILE.read_text(encoding="utf-8"))


def update_special_margins(
    customers: list[dict[str, Any]] | None = None,
    remove: list[str] | None = None,
) -> dict[str, Any]:
    """Upsert or drop special-customer margins and return the updated document.

    A customer's margin may be null to leave it PENDING; a present margin must be a
    fraction in [0, 1). Only the keys an entry actually carries are written, so a
    margin edit does not wipe the note (the override reason) and vice versa.
    Existing fields such as `source` are preserved.
    """
    payload = load_special_margins()
    rows = list(payload.get("customers", []))
    by_name = {str(c.get("name")): c for c in rows}

    for entry in customers or []:
        name = str(entry.get("name", "")).strip()
        if not name:
            raise ValueError("customer name must not be blank")
        existing = by_name.get(name)
        if existing is None:
            existing = {"name": name}
            rows.append(existing)
            by_name[name] = existing
        if "margin" in entry:
            margin = entry["margin"]
            if margin is not None:
                margin = float(margin)
                if not 0 <= margin < 1:
                    raise ValueError(f"margin for {name!r} must be in [0, 1), got {margin}")
            existing["margin"] = margin
        if "note" in entry:
            existing["note"] = entry["note"]

    if remove:
        drop = {r.strip() for r in remove}
        rows = [c for c in rows if str(c.get("name")) not in drop]

    payload["customers"] = rows
    _atomic_write_json(SPECIAL_MARGINS_FILE, payload)
    return payload


_DEPTH_WHOLE_FRACTION = re.compile(r"^(\d+)\s*-\s*(\d+)\s*/\s*(\d+)$")
_DEPTH_FRACTION = re.compile(r"^(\d+)\s*/\s*(\d+)$")


def _parse_depth_inches(text: str) -> float:
    """Turn a throat-depth label into inches: '5-3/4' -> 5.75, '5.75' -> 5.75.

    Estimators write frame depth as feet-inches fractions; the machine value has to
    stay in step with the label, so it is derived here rather than typed twice.
    """
    text = text.strip()
    try:
        value = float(text)
    except ValueError:
        whole_fraction = _DEPTH_WHOLE_FRACTION.match(text)
        fraction = _DEPTH_FRACTION.match(text)
        if whole_fraction:
            whole, num, den = (int(g) for g in whole_fraction.groups())
            if den == 0:
                raise ValueError(f"depth {text!r} has a zero denominator")
            value = whole + num / den
        elif fraction:
            num, den = (int(g) for g in fraction.groups())
            if den == 0:
                raise ValueError(f"depth {text!r} has a zero denominator")
            value = num / den
        else:
            raise ValueError(f"could not parse depth {text!r}; use e.g. 5-3/4 or 5.75")
    if value <= 0:
        raise ValueError(f"depth {text!r} must be greater than zero")
    return value


def load_finishes() -> dict[str, Any]:
    """The full finish-crosswalk document, structure preserved."""
    return json.loads(FINISHES_FILE.read_text(encoding="utf-8"))


def update_finishes(
    finishes: list[dict[str, Any]] | None = None,
    remove: list[str] | None = None,
) -> dict[str, Any]:
    """Upsert or drop finish rows (keyed by us_code) and return the updated document.

    Only the keys an entry carries are written, so editing one attribute leaves the
    others - including the US19/US26D distinction - untouched.
    """
    payload = load_finishes()
    rows = list(payload.get("finishes", []))
    by_code = {str(f.get("us_code")): f for f in rows}

    for entry in finishes or []:
        code = str(entry.get("us_code", "")).strip()
        if not code:
            raise ValueError("us_code must not be blank")
        existing = by_code.get(code)
        if existing is None:
            existing = {"us_code": code}
            rows.append(existing)
            by_code[code] = existing
        for field in ("numeric_code", "description", "premium", "note"):
            if field in entry:
                existing[field] = entry[field]

    if remove:
        drop = {r.strip() for r in remove}
        rows = [f for f in rows if str(f.get("us_code")) not in drop]

    payload["finishes"] = rows
    _atomic_write_json(FINISHES_FILE, payload)
    return payload


def load_frame_depths() -> dict[str, Any]:
    """The full wall-type-to-depth document, structure preserved."""
    return json.loads(FRAME_DEPTHS_FILE.read_text(encoding="utf-8"))


def update_frame_depths(
    wall_types: list[dict[str, Any]] | None = None,
    remove: list[str] | None = None,
) -> dict[str, Any]:
    """Upsert or drop wall-type rows (keyed by type) and return the updated document.

    `depth_inches` is derived from the `depth` label so the two cannot drift apart.
    """
    payload = load_frame_depths()
    rows = list(payload.get("wall_types", []))
    by_type = {str(w.get("type")): w for w in rows}

    for entry in wall_types or []:
        wall_type = str(entry.get("type", "")).strip()
        if not wall_type:
            raise ValueError("wall type must not be blank")
        existing = by_type.get(wall_type)
        if existing is None:
            existing = {"type": wall_type}
            rows.append(existing)
            by_type[wall_type] = existing
        if "depth" in entry:
            depth = str(entry["depth"]).strip()
            if not depth:
                raise ValueError(f"depth for {wall_type!r} must not be blank")
            existing["depth"] = depth
            existing["depth_inches"] = round(_parse_depth_inches(depth), 4)
        if "note" in entry:
            existing["note"] = entry["note"]

    if remove:
        drop = {r.strip() for r in remove}
        rows = [w for w in rows if str(w.get("type")) not in drop]

    payload["wall_types"] = rows
    _atomic_write_json(FRAME_DEPTHS_FILE, payload)
    return payload


def load_frp_constants() -> dict[str, Any]:
    """The full FRP conversion-constants document, structure preserved."""
    return json.loads(FRP_CONSTANTS_FILE.read_text(encoding="utf-8"))


def update_frp_constants(values: dict[str, Any]) -> dict[str, Any]:
    """Set FRP conversion constants and return the updated document.

    Open Item 5: these are PENDING until CBC provides them. Entering them here is
    how that owed data lands. The status flips to SET only once every constant the
    take-off actually computes with is present - a half-filled table stays PENDING,
    because a missing constant would otherwise read as a silent zero.
    """
    payload = load_frp_constants()
    for field, value in values.items():
        if field not in FRP_EDITABLE_CONSTANTS:
            raise ValueError(f"unknown FRP constant {field!r}")
        if field in FRP_NUMERIC_CONSTANTS and value is not None:
            value = float(value)
            if value < 0:
                raise ValueError(f"{field} must not be negative, got {value}")
        payload[field] = value

    complete = all(payload.get(field) is not None for field in FRP_REQUIRED_CONSTANTS)
    payload["status"] = "SET" if complete else "PENDING"
    _atomic_write_json(FRP_CONSTANTS_FILE, payload)
    return payload


def sync_vendor_categories(vendor_key: str, categories: dict[str, float]) -> None:
    """Keep vendor_tiers.json aligned when purchasing edits category multipliers."""
    if not TIERS_FILE.exists():
        return
    payload = json.loads(TIERS_FILE.read_text(encoding="utf-8"))
    for record in payload.get("vendors", []):
        if record.get("key") != vendor_key:
            continue
        record["categories"] = categories
        TIERS_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return


def stock_list_path(vendor_key: str) -> Path:
    return HARDWARE_SETS / f"{vendor_key.lower()}_top10_stock.json"


def load_stock_list(vendor_key: str) -> dict[str, Any] | None:
    path = stock_list_path(vendor_key)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def is_stock_part(vendor_key: str, part_number: str) -> dict[str, Any]:
    """NR-6 stock-list lookup. Returns None for stock when no list is on file."""
    payload = load_stock_list(vendor_key)
    if payload is None:
        return {
            "vendor": vendor_key,
            "part_number": part_number,
            "stock": None,
            "note": "No top-10 stock list on file for this vendor (NR-6 pending).",
        }

    needle = part_number.strip().upper()
    base = needle.split("-")[0].split()[0]
    parts = {
        str(item.get("part_number", "")).strip().upper()
        for item in payload.get("items", [])
        if item.get("part_number")
    }
    matched = needle in parts or base in parts
    return {
        "vendor": vendor_key,
        "part_number": part_number,
        "stock": matched,
        "list_status": payload.get("status"),
        "status_note": payload.get("status_note"),
        "source": payload.get("source"),
    }


# What architects write on a drawing, mapped to the wall types the table names.
# A schedule says "CMU", "8\" MASONRY", "MTL STUD W/ GYP" - never "masonry" on its
# own - so matching the table's labels literally finds nothing.
_WALL_TYPE_ALIASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("6\" metal stud", "6 inch metal stud", "6\" mtl stud", "6 mtl stud"),
     "6 inch metal stud with 5/8 drywall"),
    (("cmu", "masonry", "block", "brick"), "masonry"),
    (("wood stud", "wood frame", "wood-frame", "timber"), "wood-frame"),
    (("1/2\" drywall", "half inch drywall", "1/2 gyp", "half-inch drywall"),
     "half-inch drywall"),
    (("drywall", "gypsum", "gyp", "metal stud", "mtl stud", "stud"), "drywall"),
)


def depth_for_wall_type(wall_type: str | None) -> dict[str, Any] | None:
    """The frame throat a wall construction implies, or None when it is unclear.

    Never guesses. The table says so itself - "Do NOT guess a depth. Flag the
    opening for estimator review" - because a frame ordered to the wrong throat
    does not fit the wall, and that is discovered on site.

    Aliases are ordered most specific first: a schedule reading
    "6\" METAL STUD W/ 5/8\" GYP" must not match the bare "stud" rule and come
    back 5-7/8 when the table says 8-1/4.
    """
    if not wall_type or not str(wall_type).strip():
        return None
    text = " ".join(str(wall_type).lower().split())

    table = load_frame_depths()
    by_type = {str(w.get("type", "")).lower(): w for w in table.get("wall_types", [])}

    if text in by_type:
        return dict(by_type[text])
    for needles, canonical in _WALL_TYPE_ALIASES:
        if any(needle in text for needle in needles):
            entry = by_type.get(canonical)
            if entry:
                return {**entry, "matched_on": canonical}
    return None
