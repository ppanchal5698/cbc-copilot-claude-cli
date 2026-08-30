# MCP Server Contracts

Six stdio servers. Every tool that reads a PDF returns `source_page` (NFR-3).
Schemas live in each server's `tools.py`; this document is the reference.

---

## pdf-tools

Reads bid-set PDFs. Architectural sheets are CAD exports, so table extraction
clusters positioned words rather than detecting ruled tables.

### `extract_text(file_path, pages?)`
Falls back to OCR only when a page has no extractable text.

```json
{ "file": "...", "page_count": 30,
  "pages": [{ "source_page": 14, "text": "...", "ocr_used": false, "char_count": 9633 }] }
```

### `extract_tables(file_path, page_range?, region?)`
`page_range` accepts `"14"`, `"1-30"`, `"all"`. `region` is `[x0,y0,x1,y1]` in points.

```json
{ "file": "...", "method": "word-position clustering",
  "pages": [{ "source_page": 14, "row_count": 235,
    "rows": [{ "y": 609.8, "x_start": 640.2,
               "cells": ["01 3' - 6\"", "7' - 0\"", "A", "1", "TEMP. HM HMD", "GROUP 1"],
               "text": "01 3' - 6\" | 7' - 0\" | A | 1 | TEMP. HM HMD | GROUP 1" }] }] }
```

### `get_page_image(file_path, page_number, dpi=200, out_dir?)`
```json
{ "source_page": 14, "image_path": "...", "dpi": 200, "file": "..." }
```

### `search_pdf(file_path, query, context_chars=500)`
```json
{ "file": "...", "query": "DOOR SCHEDULE", "hit_count": 14,
  "hits": [{ "source_page": 14, "offset": 2086, "context": "..." }] }
```

### `find_sheets(file_path, queries?)`
Ranks pages by how many schedule-related terms they carry. Cheap first step before
`extract_tables`.

```json
{ "file": "...", "pages": [{ "source_page": 15, "score": 12, "terms": ["door", "schedule"] }],
  "not_found": [] }
```

### `get_page_size(file_path, page_number)`
Page dimensions in PDF points - required to interpret bbox coordinates.

```json
{ "source_page": 15, "width": 2592.0, "height": 1728.0, "page_count": 30 }
```

Row objects from `extract_tables` also include `bbox`, `cell_boxes` and
`page_size` for NFR-3 provenance.

---

## pricebook

Cost path 2: `cost = list price x multiplier tier`. Read-only against
`pricebooks/`. Page text is cached in-process on first touch.

### `list_vendors()`
```json
{ "pricebook_dir": "...", "count": 26,
  "pricebooks": [{ "vendor": "hager", "name": "Hager Door Hardware Price Book #18",
                   "file": "hager_price_book_18.pdf", "effective_date": "2026-02-02",
                   "kind": "price_book", "multiplier": null,
                   "multiplier_note": "Priced by product category..." }] }
```

### `search_product(query, vendor?, division?, limit=10)`
Fuzzy match via stdlib `difflib`; exact containment scores 1.0.
```json
{ "query": "4040XP", "hit_count": 29,
  "hits": [{ "vendor": "hager", "source_file": "...", "source_page": 132,
             "effective_date": "2026-02-02", "line": "...", "score": 1.0 }] }
```

### `lookup_pricing(part_number, vendor, category?)`
Returns every price candidate found. **Computes `net_cost` only when the match is
unambiguous** - one match with one price. Otherwise `cost_source` is `MANUAL`.
Adders are never included.
```json
{ "part_number": "3510", "vendor": "hager", "match_count": 25,
  "matches": [{ "source_page": 297, "context": "...", "list_price_candidates": [227.72] }],
  "multiplier": 0.29, "multiplier_tier": "locks",
  "multiplier_effective_date": "2026-03-02",
  "list_price": null, "net_cost": null, "cost_source": "MANUAL", "note": "..." }
```

### `get_multiplier(vendor, tier?)`
Hager prices by category, so pass one: `locks` 0.290, `door_controls` 0.300,
`exit_devices` 0.3005, `electrified_products` 0.410, `auto_operators` 0.400,
`architectural_hinges` 0.210, `residential_hinges` 0.375.
An unknown vendor or category returns `multiplier: null` plus a note - **never a guess**.

---

## calc-engine

Pure computation, no external dependencies. The only quote arithmetic in the system.

### `calculate_line(cost, margin, quantity=1)`
```json
{ "cost": 74.33, "margin": 0.27, "divisor": 0.73, "quantity": 3,
  "sale_ea": 101.82, "unit_sale_ea": 101.82, "ext_price": 305.46,
  "formula": "sale_ea = cost / (1 - margin); ext_price = sale_ea * quantity" }
```
Raises on `margin >= 1` (divide by zero) and on a negative cost.

### `apply_margin(cost, product_type, override_margin?, override_reason?)`
`product_type` is one of `commodity` (0.27), `restroom_partitions` (0.35),
`specialty` (0.40), `custom_built` (0.25), `accessories` (0.56). Bands are read
from `reference-library/margins/margin_framework.json`.
Adds `warning` when a margin is overridden with no reason recorded.

### `compute_totals(line_items, project_state?)`
```json
{ "groups": [{ "group": "Door 01", "line_count": 2, "subtotal": 505.46 }],
  "subtotal": 605.46, "freight": null,
  "freight_note": "TBD - freight is not quoted at estimate stage",
  "project_state": "OH", "tax_rate": 0.08, "tax": 48.44,
  "tax_note": "...", "grand_total": 653.90 }
```
Tax applies to **OH (8%)** and **KY (6.5%)** only. An unknown state yields
`project_state: null` and a tax note saying UNRESOLVED - not a silent zero.

### `validate_margin(product_type, applied_margin)`
```json
{ "status": "fail", "floor": 0.27, "applied_margin": 0.20,
  "flag": "below_band", "note": "Flagged only. Approval routing is deferred (NFR-8)." }
```

---

## artifact-storage

Project writes with SHA-256 version history. Refuses any path that escapes
`projects/{project}/`.

### `save_artifact(project, path, content, version_note?)`
```json
{ "project": "...", "path": "extracted/door_schedule.json", "absolute_path": "...",
  "sha256": "...", "bytes": 4096, "unchanged": false, "saved_at": "..." }
```
Identical content is written but not re-versioned (`unchanged: true`).

### `get_artifact(project, path, version?)`
`version` is a SHA-256 prefix. Without it, returns the live file.

### `list_versions(project, path)` - newest first, from an append-only index.

### `list_project_files(project, subdir?)` - paths and sizes, excluding `.versions/`.

---

## p21-connector

**READ-ONLY.** No create, update or delete tool exists, and an import-time
assertion fails the server if one is ever added.

### `lookup_last_po(part_number, vendor?)`
With `P21_BASE_URL` unset - the state today - returns:
```json
{ "part_number": "3510", "vendor": "hager", "last_po_price": null, "po_date": null,
  "freshness_status": "unknown", "item_id": null, "connected": false,
  "cost": null, "cost_source": "MANUAL", "action_required": "manual_price_entry",
  "prompt": "price may be out of date - refresh",
  "reason": "P21 is not connected in this environment...",
  "fallbacks": ["Path 2: vendor list price x multiplier tier",
                "Path 3: distributor lookup or vendor RFQ"] }
```

### `check_freshness(po_date)`
```json
{ "po_date": "2026-03-14", "age_days": 165, "freshness_status": "fresh",
  "usable": true, "guidance": "Usable if there has been no price increase.",
  "rule": "under ~6 months fresh; ~6-8 months+ unreliable; 3-4 years discard" }
```
Bands: `fresh` <=180d, `unreliable` <=1095d, `stale` beyond, plus `future_dated`.

### `search_item(query, limit=10)`
Returns results plus the known risks: P21 item IDs frequently differ from
manufacturer part numbers, semi-custom items will not match, and manual entry must
stay available.

---

## catalog

**READ-ONLY.** Live MongoDB catalog for Ops-Hub pricing passes. The API and
ingest jobs own writes; Claude reads current multipliers and product costs here
during `match_and_price` jobs.

### `search_products(query, division?, manufacturer?, limit=20)`
```json
{ "query": "4040XP", "hit_count": 3,
  "hits": [{ "part": "4040XP", "manufacturer": "LCN", "cost": 412.50,
             "list_price": 1375.00, "multiplier": 0.30, "price_book": "..." }] }
```

### `get_product(part)`
Exact part lookup with price book, multiplier tier, and cross-references.

### `get_multiplier(vendor, category?)`
Returns the current tier for a vendor (and category when applicable). Unknown
tiers return `null` with a note — never a guess.

### `list_price_books(vendor?)`
All price books and multiplier programs with effective dates and staleness hints.

---

## Shared runtime

`mcp-servers/_runtime.py` provides `serve(name, TOOLS, HANDLERS)` — the stdio
wiring and error envelope shared by all six servers. A handler exception is
returned as `{"error": ..., "tool": ..., "arguments": ...}` with `is_error: true`
rather than crashing the server.

Verify every contract:

```bash
python mcp-servers/main.py --selftest
```
