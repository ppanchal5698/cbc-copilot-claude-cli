# MCP Server Contracts

Five stdio servers registered in [`.mcp.json`](../.mcp.json). Schemas live in
each server's `tools.py`; worker jobs scope subsets via
[`src/cbc/core/toolsets.py`](../src/cbc/core/toolsets.py).

**Pricing model:** The **catalog** server routes to vendor PDF pages (PageIndex in
MongoDB). It does **not** return prices. An agent opens the page with **pdf-tools**,
reads the list price, then **calc-engine** applies multiplier and margin.

---

## pdf-tools (6 tools)

Reads bid-set and price-book PDFs. Table extraction clusters positioned words.

| Tool | Notes |
|---|---|
| `find_sheets` | Term-count page map; use before reading |
| `extract_text` | Max 4 pages/call; `pages` accepts `"14"`, `"1-30"`, `"all"` |
| `extract_tables` | Max 4 pages, 300 rows/page; returns `pages_deferred` when capped |
| `get_page_image` | Render page for visual confirmation |
| `get_page_size` | Points; required for bbox normalization |
| `search_pdf` | Max 40 hits; default `context_chars` **160** |

Every result includes `source_page` (NFR-3).

---

## catalog (7 tools, read-only)

Page-index navigation over uploaded price books. Requires `MONGODB_READONLY_URI`.

| Tool | Returns prices? |
|---|---|
| `list_catalogs` | No |
| `get_catalog_overview` | No |
| `find_pages` | No — ranked pages with `file_path`, `pdf_page`, `locator` |
| `get_page` | No — index metadata for one page |
| `get_multiplier` | Multiplier only; arg **`category`** (Hager: locks, exit_devices, …) |
| `get_special_net` | Fixed net override when present |
| `is_stock_item` | Boolean vs NR-6 stock list |

---

## calc-engine (6 tools)

Adapter over [`src/cbc/core/calc.py`](../src/cbc/core/calc.py) — single money math.

| Tool | Purpose |
|---|---|
| `cost_from_list` | `(list + adders) × multiplier` — adders on list first (NR-4) |
| `lookup_lite_kit_list_price` | NR-1 lite/louver list price from `lite_kit_prices.json` |
| `calculate_line` | `sale_ea = cost / (1 - margin)` |
| `apply_margin` | Product-type band + optional override |
| `compute_totals` | Per-group subtotals; OH/KY tax only |
| `validate_margin` | Flag below-band (NFR-8 deferred routing) |

---

## artifact-storage (4 tools)

Versioned writes under `projects/{slug}/`. `save_artifact` rejects placeholder content.

---

## p21-connector (3 tools, read-only)

| Tool | Purpose |
|---|---|
| `lookup_last_po` | Path 1 cost (FR-6) |
| `check_freshness` | PO age rule |
| `search_item` | Part lookup; returns MANUAL when disconnected |

No write/update tools are registered or permitted.

---

## Job → server scoping

| Job type | Servers |
|---|---|
| `extract_bid_set`, `rerun_extraction`, `ingest_addendum` | pdf-tools, artifact-storage |
| `match_and_price`, `run_full_pipeline` | all five |
| `build_proposal` | calc-engine, artifact-storage |
| `ingest_pricebook` | catalog, pdf-tools, artifact-storage |

`match_and_price` **fails fast** when `MONGODB_READONLY_URI` is unset (catalog unavailable).
