# MASTER BUILD PROMPT — CBC Estimating Copilot
# Feed this file to Claude Code CLI to bootstrap the entire system.
#
# Usage:
#   claude -p "$(cat docs/bootstrap/BUILD_PROMPT.md)" --dangerously-skip-permissions
#
# Or interactively:
#   claude
#   > Read docs/bootstrap/BUILD_PROMPT.md and execute it.
#
# Required reference files (already in repo):
#   - docs/architecture_source.md  (the architecture document)
#   - docs/CBC_Req_Validation_v1_3.xlsx  (requirements & process flow)
#   - tests/fixtures/pdfs/1_Architectural.pdf  (sample building plan)
#   - pricebooks/hager_price_book_18.pdf  (product catalog)

---

## PHASE 0 — CONTEXT INGESTION (do this before writing any code)

You are an expert software architect building an autonomous estimating system called the **CBC Estimating Copilot**. This system will be autopiloted by Claude Code CLI in the background to process building-plan PDFs, extract Division 8/9/10 product data, match products against vendor price books, price every line, and generate reviewable draft quotations — following the exact manual workflow that a CBC estimator follows.

Before writing a single line of code, read and internalize these files in order:

1. **`docs/architecture_source.md`** — This is the master architecture document. It contains the complete folder structure, every agent definition, every skill, every rule, every hook, every MCP server contract, the headless pipeline configuration, and the data-flow diagram. Treat it as the single source of truth for what to build.

2. **`docs/CBC_Req_Validation_v1_3.xlsx`** — The validated requirements workbook from Hamilton Parker / CBC. It contains:
   - **Requirements Matrix tab**: 54 requirements (FR-1 through FR-16, NFR-1 through NFR-11) with estimator confirmations. Read every row.
   - **Process Flow tab**: Phase 0 (Intake) through Phase 6 (Deliver) with exact step-by-step activities, tools, and outputs.
   - **Product Scope tab**: In-scope and out-of-scope manufacturers and categories.
   - **Assumptions & Dependencies tab**: What must be true for the system to work.
   - **Open Items tab**: Items still pending (fire rating 7.3, alternates/addenda 4.1).
   Extract the margin bands, vendor tiers, frame depths, door notation rules, finish nomenclature, cost-sourcing paths, and the manual cut-off principle.

3. **`tests/fixtures/pdfs/1_Architectural.pdf`** — A real building plan (Dutch Bros Coffee, Alexandria LA). Use this as the test fixture. It contains door schedules, frame schedules, hardware sets, Division 10 specialties, FRP wall panel details, and fire-rated openings.

4. **`pricebooks/hager_price_book_18.pdf`** — The Hager price book (744 pages). Hager is 75% of CBC's volume. Use this to understand the price-book PDF structure. (no more than 30 lines) summarizing:
- The build order you will follow
- Key technical decisions (libraries, frameworks)
- Any ambiguities you resolved and how
- Acceptance criteria you will validate against

Do NOT proceed to Phase 1 until you have output this plan.

---

## PHASE 1 — SCAFFOLD THE FOLDER STRUCTURE

Create the complete directory tree exactly as specified in `docs/architecture_source.md`. Every directory and file must exist. Create placeholder files where content will be filled in later phases. Specifically:

```
cbc-estimating-copilot/
├── CLAUDE.md
├── .claude/
│   ├── settings.json
│   ├── settings.local.json          (gitignored, stub only)
│   ├── agents/                      (9 .md files)
│   ├── skills/                      (9 skill directories, each with SKILL.md)
│   ├── rules/                       (8 .md files)
│   ├── hooks/                       (5 .sh files, chmod +x)
│   └── memory/                      (13 .md files)
├── mcp-servers/                     (5 server directories + shared config)
├── workflows/                       (8 .sh files + README.md)
├── pricebooks/                      (README.md placeholder)
├── reference-library/               (7 subdirectories with .json files)
├── projects/                        (.gitkeep)
├── templates/                       (3 template files)
├── scripts/                         (4 utility scripts)
├── docs/                            (7 .md files)
├── tests/                           (test files)
├── .gitignore
└── README.md
```

Run `find . -type f | sort` after scaffolding and verify every path matches the architecture document.

---

## PHASE 2 — BUILD CLAUDE.md AND MEMORY FILES

### CLAUDE.md (root project memory)
Write a concise CLAUDE.md (under 200 lines) that serves as the project index. It must contain:
- One-paragraph system description
- Architecture layers summary (7 layers with paths)
- Non-negotiable guardrails (NFR-1, NFR-2, NFR-3, NFR-5, NFR-8) — each one sentence
- Key reference paths using `@` imports for the most important docs
- Scope: in-scope and out-of-scope product categories
- Vendor priority list (top-10 for Phase 1)
- Manual cut-off principle (beyond top-10 → MANUAL path)

### Memory files (`.claude/memory/`)
Write all 13 memory files with content extracted from the requirements workbook:

1. **`project_context.md`** — CBC identity, Hamilton Parker, national-accounts scope, 1865 Leonard Ave Columbus OH
2. **`estimator_profiles.md`** — Kevin (one-off from scratch), Rick (own Excel), Shanna (templated mode); exceptions: McDonalds, Cava
3. **`vendor_tiers.md`** — All active vendor tiers from the workbook: Hager, ASI, NGP, PEMKO/Markar, Rockwood, Bobrick, Bradley, Gamco. Include multiplier values where stated (e.g., World Dryer L3 = 0.339)
4. **`margin_sheet.md`** — 4 bands: Commodity 0.73, Restroom partitions 0.65, Specialty 0.60, Custom 0.75. Note: Accessories derive to 56%. Margin is OVERRIDABLE per quote by sourcing.
5. **`frame_depths.md`** — 5 standard throat sizes: 5-5/8 (half-inch drywall), 5-3/4 (masonry), 5-7/8 (drywall), 7-3/4 (wood-frame), 8-1/4 (6" metal stud 5/8 drywall). CUSTOM option (10 sizes max). Adjustable frames exist.
6. **`door_notation.md`** — 4-digit shorthand: first 2 digits = width (feet-inches), last 2 = height (feet). 3070 = 3'-0" × 7'-0", 3670 = 3'-6" × 7'-0"
7. **`finish_nomenclature.md`** — Dual system: US26D ↔ 626, US19 ↔ 619, US15. Note: US19 vs 26D are DIFFERENT satins. Some finishes are premium with lead times.
8. **`fire_rating_rules.md`** — 20/45/60/90-minute UL labels. Rating drives product selection AND price. Unrated match on a rated opening = defect. Status: still pending dedicated answer (Matrix 7.3).
9. **`handing_codes.md`** — LH, RH, LHR, RHR. Appears per opening in the schedule. Derivable from plan when missing.
10. **`cost_sourcing_rules.md`** — Three paths: (1) P21 last-PO if sold within ~24 months, no price increase (~90% correct); (2) list × multiplier for non-special items; (3) vendor RFQ for custom/never-sold/special-prep. Freshness rule: more than 24 months unreliable, more than 2.5 years discard. Distributor-bought lines (Banner, SecLock, Pionite, Wilsonart) need MANUAL price entry with "price may be out of date" refresh prompt.
11. **`manual_cutoff.md`** — Beyond top-10 stock items → MANUAL path. Do NOT attempt to price every option permutation. Estimator handles the long tail. Hard cut-off for custom sizes (9-ft doors), unusual preps, options not sold in years (e.g., electric latch retraction).
12. **`sales_tax_rules.md`** — Supply-only material (not installed labor). Sales tax ONLY for Ohio (8%) and Kentucky (6.5%), border-nexus. Other 48 states + Canada: no tax. Sale is to GC/corporation, not end customer.
13. **`process_flow.md`** — Phase 0 (Intake) → Phase 1 (File setup) → Phase 2 (Spec scoping) → Phase 3 (Drawing take-offs) → Phase 3b (FRP take-off) → Phase 4 (Pricing build) → Phase 4b (Alternates/addenda) → Phase 5 (Judgment/reuse/RFIs) → Phase 6 (Deliver). Include the system/tool and output for each phase.

---

## PHASE 3 — BUILD ALL 9 AGENTS

Each agent is a Markdown file in `.claude/agents/` with YAML frontmatter (`name`, `description`, `model: sonnet`) and a system prompt. Write complete, production-quality prompts for each:

1. **`intake-coordinator.md`** — Phase 0. Receives bid request (email PDF or phone-in), creates project directory scaffold under `projects/{project_name}/`, moves uploaded PDFs to `uploads/raw/`, extracts metadata (project name, location, architect, GC, bid due date, bid alternates). Writes `projects/{project_name}/extracted/scope_metadata.json`. Tools: artifact-storage MCP, file operations.

2. **`spec-scope-analyst.md`** — Phase 2. Parses specification PDFs to identify Division 08 (doors, frames, hardware) and Division 10 (specialties, partitions, accessories, washroom equipment) sections. Extracts fire ratings from door/frame schedules. Extracts hardware-set callouts (HW-1, HW-2, etc.). Confirms scope boundaries (in-scope vs out-of-scope per rules). Writes `extracted/scope_summary.json`. Tools: pdf-tools MCP. References: scope-boundaries rule, fire_rating_rules memory.

3. **`takeoff-engineer.md`** — Phase 3. Reviews architectural drawings (floor plans, elevations, schedules). Extracts door opening schedule: door number, size (4-digit notation), handing, finish, fire rating, hardware-set callout, frame type, wall type (for frame depth derivation). Converts 4-digit notation to width/height. Flags missing ratings/handing/finish. Writes `extracted/door_schedule.json`. Tools: pdf-tools MCP. References: door_notation, frame_depths, handing_codes, finish_nomenclature memory.

4. **`frp-specialist.md`** — Phase 3b. Where FRP is specified, extracts perimeter linear feet, inside corners, outside corners from drawings. Converts geometry to material quantities using conversion constants (panel size, waste %, trim stick lengths, adhesive coverage). Writes `extracted/frp_takeoff.json`. Tools: pdf-tools MCP. References: frp_constants. Note: constants are PENDING from CBC — structure the JSON to accept them when provided.

5. **`product-matcher.md`** — FR-4. Matches each extracted opening to the closest entry in the reference library (hardware_sets JSON files). Matching respects: fire rating, handing, finish, product type/series, manufacturer preference (Hager first). Proposes corresponding line items. Assigns confidence score per match. Flags low-confidence matches for review. Writes `extracted/hardware_sets.json`. Tools: pricebook MCP. References: vendor_tiers, fire_rating_rules memory.

6. **`pricing-engineer.md`** — Phase 4. Prices every line item using three cost paths: (1) P21 last-PO lookup, (2) list × customer-specific multiplier, (3) vendor RFQ flag for manual pricing. Applies the product-type margin framework as editable default per line. Handles manual adders (electrification, NRP hinges, premium finishes). Honors freshness rule. Records cost source and date for auditability. Handles distributor-bought lines with manual entry + refresh prompt. Writes `priced/line_items.json` and `priced/margin_applied.json`. Tools: p21-connector MCP, pricebook MCP, calc-engine MCP. References: cost_sourcing_rules, margin_sheet, manual_cutoff memory.

7. **`quote-builder.md`** — Phase 4/6. Builds the draft quotation grouped by door with subtotals, a separate restroom-accessories block, and a freight line (usually TBD/omitted at estimate stage). Computes: Sale EA = Cost / (1 - margin), Unit Sale EA, Ext = Unit × Qty, Sub-totals, Grand total. Renders quotation HTML using Jinja2 template. Writes `projects/{project}/quotation.html`. Tools: calc-engine MCP, artifact-storage MCP. References: templates/quotation.html.

8. **`quality-reviewer.md`** — Phase 5 / FR-8 / FR-9. Assigns confidence scores to every match. Flags: low-confidence matches, missing fire ratings, unparsed content, below-band margins. Generates review interface (HTML) with accept/edit/delete/add capabilities. Captures estimator corrections as structured feedback. Searches for closest prior quote (same brand/architect/GC) for reuse. Writes `review/review_flags.json` and `review/review_summary.html`. Tools: none external — pure analysis. References: accuracy-trust rule.

9. **`delivery-agent.md`** — Phase 6 / FR-10. Exports the approved quotation to PDF in the customer-facing format with standard commercial terms (HP PO required, 30-day validity). Prepares email body for routing to the sales initiator (NOT a group email — specific person from the queue). HALTS before sending — draft only, estimator must approve. Writes `projects/{project}/quotation.pdf` and `projects/{project}/uploads/final/`. Tools: artifact-storage MCP. References: human-in-the-loop rule, sales_tax_rules memory.

---

## PHASE 4 — BUILD ALL 9 SKILLS

Each skill is a directory under `.claude/skills/` containing `SKILL.md` with YAML frontmatter (`name`, `description`), plus `scripts/` and `references/` subdirectories where needed.

1. **`extract-door-schedule/`** — SKILL.md with extraction steps, `scripts/parse_schedule.py` (uses pdfplumber + tabula to extract door/frame schedule tables from PDFs, handles both native and scanned PDFs with OCR fallback via pytesseract), `references/schedule_anatomy.md` (4-digit notation, HW-set anatomy, field definitions).

2. **`match-hardware-sets/`** — SKILL.md with matching algorithm (exact match on part number → fuzzy match on function+finish+rating → flag for review), `references/hw_set_library.md` (standard set composition: hinges, lock/exit device, closer, kick plate, threshold, sweep, weatherstrip, smoke seal, floor stop, silencers).

3. **`scan-product-catalog/`** — SKILL.md with price-book search strategy (keyword search → part number lookup → multiplier application), `scripts/search_pricebook.py` (indexes price-book PDFs with page-level traceability, supports fuzzy part-number matching).

4. **`price-line-item/`** — SKILL.md with the three cost-path decision tree, `references/cost_paths.md` (Path 1: P21 last-PO if sold <1yr, Path 2: list×multiplier, Path 3: vendor RFQ flag, freshness rule, distributor-bought manual entry).

5. **`apply-margin/`** — SKILL.md with margin application logic, `references/margin_bands.md` (Commodity 0.73, Restroom 0.65, Specialty 0.60, Custom 0.75, Accessories 56%, overridable per quote by sourcing).

6. **`frp-takeoff/`** — SKILL.md with FRP calculation steps, `references/frp_constants.md` (placeholder structure: panel_size, waste_pct, trim_stick_length, adhesive_coverage_sqft_per_unit — marked PENDING from CBC).

7. **`generate-quotation/`** — SKILL.md with quote rendering pipeline, `scripts/render_quote.py` (Jinja2 template renderer: reads priced/line_items.json + margin_applied.json, renders templates/quotation.html, outputs projects/{project}/quotation.html).

8. **`validate-extraction/`** — SKILL.md with validation checklist, `references/validation_rules.md` (required fields per opening: door_number, size, handing, finish, fire_rating, hardware_set; flag if any missing; verify rating not silently dropped on rated openings).

9. **`reuse-prior-quote/`** — SKILL.md with prior-quote search logic (match on brand, architect, GC; return closest match as starting draft per FR-11).

---

## PHASE 5 — BUILD ALL 8 RULES

Each rule is a Markdown file in `.claude/rules/`. Write production-quality constraint definitions:

1. **`human-in-the-loop.md`** — NFR-1: No quote sent without explicit estimator approval. Copilot drafts, sources, calculates — does not send. Enforcement: pre_send_quote.sh hook. Owner: Estimating.
2. **`accuracy-trust.md`** — NFR-2: Confidence scoring visible from day one. Unmatched/low-confidence items never silently guessed. Hard cut-off leaves complex items manual. Owner: Estimating.
3. **`auditability.md`** — NFR-3: Every generated line traceable to source drawing page AND reference-library price-sheet version (including vendor multiplier tier + effective date). Audit trail logged to `audit_trail.jsonl`. Owner: Estimating + IT.
4. **`p21-read-only.md`** — NFR-5: P21 access is READ-ONLY. No write-back initially. P21 item IDs often differ from manufacturer part numbers — semicustom items won't match. Manual entry must always be available. Owner: IT + Dash.
5. **`margin-governance.md`** — NFR-8: Margin floor per product type. Below-band pricing flagged. Deferred to future phase (no deviation today — estimators hold standard margins). Owner: future.
6. **`data-stewardship.md`** — NFR-10: Named owner + refresh cadence per pricing source (reference library, vendor multiplier sheets, margin sheet). Stale price sheets drive wrong quotes. Status: OPEN — owner and cadence not yet assigned. Owner: Purchasing + Estimating.
7. **`scope-boundaries.md`** — In-scope: metal/wood doors, HM frames (welded/knock-down), door hardware, Division 10 specialties, restroom partitions/accessories, hand dryers, FRP wall panels. Out-of-scope: ceiling tile/grid, tile, brick, masonry, aluminum storefront, coiling/overhead doors, engineered wood, metal siding, Scranton (access lost).
8. **`file-safety.md`** — Never delete files outside `./projects/{project}/`. Limit writes to the current project worktree. Never write to `pricebooks/` or `reference-library/` during a pipeline run (those are read-only reference data). Raw uploads preserved immutably.

---

## PHASE 6 — BUILD ALL 5 GUARDRAIL HOOKS

Each hook is an executable shell script in `.claude/hooks/` (chmod +x). Configure them in `.claude/settings.json` under the `hooks` key.

1. **`pre_send_quote.sh`** — PreToolUse hook, matcher: `Bash`. Blocks any command matching `sendmail|mailx|mutt|msmtp|postfix|curl.*mail|smtp`. Also blocks MCP tools matching `send|email|mail`. Exit code 2 = block. Message: "BLOCKED: Sending quotations requires explicit estimator approval (NFR-1)."

2. **`pre_delete_guard.sh`** — PreToolUse hook, matcher: `Bash`. Blocks `rm -rf` outside `projects/`. Blocks `git push`. Blocks `rm` on anything in `pricebooks/` or `reference-library/`. Exit code 2 = block. Message: "BLOCKED: File deletion outside project scope is prohibited (file-safety rule)."

3. **`post_extraction_validate.sh`** — PostToolUse hook, matcher: `Write|Edit`. When a file is written to `extracted/`, runs `python scripts/validate_project.py --check-extraction {project}`. Validates required fields, checks for missing fire ratings. Exit code 0 = pass, non-zero = warning in stderr (does not block).

4. **`post_quote_format.sh`** — PostToolUse hook, matcher: `Write|Edit`. When `quotation.html` is written, runs `python -m pyhtmlbeautifier` if available, or `prettier --parser html` if available. Exit code 0 = pass.

5. **`log_audit_trail.sh`** — PostToolUse hook, matcher: `*` (all tool calls). Appends a JSONL line to `projects/{project}/audit_trail.jsonl` with: timestamp, tool_name, tool_input_summary, agent_name (from context). Uses `jq` to parse the hook input. Exit code 0 always (logging never blocks).

---

## PHASE 7 — BUILD ALL 5 MCP SERVERS

Each MCP server is a Python package in `mcp-servers/` with `server.py` (MCP server using the `mcp` Python SDK), `tools.py` (tool definitions with input schemas), and `requirements.txt`. Use the standard MCP server pattern with stdio transport.

1. **`pdf-tools/server.py`** — Tools: `extract_text(file_path, pages?)`, `extract_tables(file_path, page_range?)`, `get_page_image(file_path, page_number, dpi=200)`, `search_pdf(file_path, query, context_chars=500)`. Uses: pdfplumber for text/tables, PyMuPDF (fitz) for page images, pytesseract for OCR fallback on scanned pages. Every output includes `source_page` for auditability.

2. **`pricebook/server.py`** — Tools: `search_product(query, vendor?, division?)`, `get_multiplier(vendor, tier)`, `lookup_pricing(part_number, vendor)`, `list_vendors()`. Maintains an in-memory index of price-book PDFs in `pricebooks/`. Uses: pdfplumber for text extraction, rapidfuzz for fuzzy part-number matching. Returns: part_number, description, list_price, multiplier, net_cost, source_page, effective_date.

3. **`calc-engine/server.py`** — Tools: `calculate_line(cost, margin, quantity)`, `apply_margin(cost, product_type, override_margin?)`, `compute_totals(line_items)`, `validate_margin(product_type, applied_margin)`. Pure computation — no external dependencies. Returns: sale_ea, ext_price, subtotal, grand_total, margin_check (pass/fail vs floor).

4. **`artifact-storage/server.py`** — Tools: `save_artifact(project, path, content, version?)`, `get_artifact(project, path, version?)`, `list_versions(project, path)`, `list_project_files(project)`. Stores files under `projects/{project}/`. Maintains version history with SHA-256 hashing. Append-only audit log.

5. **`p21-connector/server.py`** — Tools: `lookup_last_po(part_number)`, `check_freshness(po_date)`, `search_item(query)`. READ-ONLY — no write tools. Returns: last_po_price, po_date, freshness_status (fresh/unreliable/stale based on 6-8 month rule), item_id, note if item_id ≠ mfr_part_number. If P21 is not connected, returns a structured "manual entry required" response with refresh prompt.

### Shared MCP infrastructure
- **`mcp-servers/pyproject.toml`** — Shared Python project with dependencies: `mcp`, `pdfplumber`, `PyMuPDF`, `pytesseract`, `rapidfuzz`, `jinja2`, `openpyxl`, `pandas`, `Pillow`.
- **`mcp-servers/main.py`** — Development orchestrator that starts all 5 servers simultaneously for local testing.
- **`mcp-servers/README.md`** — Setup instructions including `claude mcp add` commands for each server.

---

## PHASE 8 — BUILD REFERENCE LIBRARY (structured JSON)

Populate `reference-library/` with JSON files extracted from the requirements workbook and price books:

1. **`hardware_sets/hager_top10_stock.json`** — Top-10 stock items per product type (locks, exits, closers, hinges, kick plates, thresholds, sweeps, weatherstrip, silencers). Structure: `[{ "category": "lock", "part_number": "3500", "series": "3500", "description": "...", "grade": 1, "stock": true }]`. Extract part numbers from the Hager price book.

2. **`hardware_sets/allegion_stock.json`** — Same structure for Allegion (Von Duprin, LCN, Schlage, Ives).

3. **`hardware_sets/custom_other_matrix.json`** — Full option matrix: function, backset, finish, lever, keyway, strike, electrified options. Structure: `{ "functions": [...], "finishes": [...], "levers": [...], "keyways": [...], "strikes": [...], "electrified": [...] }`.

4. **`margins/margin_framework.json`** — `{ "bands": [{ "name": "Commodity", "divisor": 0.73 }, { "name": "Restroom Partitions", "divisor": 0.65 }, { "name": "Specialty", "divisor": 0.60 }, { "name": "Custom-built", "divisor": 0.75 }], "accessories_derived": 0.56, "overridable": true, "override_reason": "sourcing" }`.

5. **`multipliers/vendor_tiers.json`** — `{ "vendors": [{ "name": "Hager", "tier": "...", "multiplier": null, "note": "75% of volume, custom-negotiated pricing" }, { "name": "World Dryer", "tier": "L3", "multiplier": 0.339 }] }`. Fill in known multipliers from workbook; mark unknowns as null with note.

6. **`multipliers/special_customer_margins.json`** — `{ "customers": [{ "name": "Wendy's", "note": "special margin when bought via Banner/SecLock at higher cost" }] }`.

7. **`frame_depths/wall_type_to_depth.json`** — `{ "wall_types": [{ "type": "half-inch drywall", "depth": "5-5/8", "note": "common at McDonalds" }, { "type": "masonry", "depth": "5-3/4" }, { "type": "drywall", "depth": "5-7/8" }, { "type": "wood-frame", "depth": "7-3/4" }, { "type": "6\" metal stud 5/8 drywall", "depth": "8-1/4" }], "custom_option": true, "custom_max": 10 }`.

8. **`finishes/finish_crosswalk.json`** — `{ "finishes": [{ "us_code": "US26D", "numeric_code": "626", "description": "satin chrome", "premium": false }, { "us_code": "US19", "numeric_code": "619", "description": "different satin", "premium": false, "note": "US19 vs 26D are DIFFERENT satins" }, { "us_code": "US15", "numeric_code": null, "description": "...", "premium": false }] }`.

9. **`frp_constants/conversion_constants.json`** — `{ "status": "PENDING", "panel_size": null, "waste_pct": null, "trim_stick_length": null, "adhesive_coverage_sqft_per_unit": null, "note": "Constants still to be provided by CBC (Shanna/Vu360)" }`.

10. **`adders/manual_adders.json`** — `{ "adders": [{ "type": "electrification", "note": "not in base price book" }, { "type": "non-removable-pin hinges (NRP)", "note": "added on top of base price" }, { "type": "premium/lead-time finishes", "note": "added on top of base price" }] }`.

11. **`prior_quotes/.gitkeep`** — Empty, for future quote library.

---

## PHASE 9 — BUILD WORKFLOWS AND HEADLESS PIPELINE

Write the orchestration scripts in `workflows/`:

1. **`run_full_pipeline.sh`** — Main entrypoint. Takes `<project_name>` as argument. Runs Claude Code in headless mode (`claude --print --dangerously-skip-permissions`) with a prompt that instructs the orchestrator to: process PDFs in `projects/{name}/uploads/raw/`, follow Phase 0→6 using the agents in `.claude/agents/`, skills in `.claude/skills/`, respect all rules and hooks, write outputs to `projects/{name}/`, generate draft quotation, HALT before sending (Phase 6 = draft ready for review), log to `audit_trail.jsonl`.

2. **`phase0_intake.sh`** through **`phase6_deliver.sh`** — Individual phase scripts that can be run independently. Each invokes Claude Code headless with a phase-specific prompt that delegates to the corresponding agent.

3. **`watch_uploads.sh`** — Uses `inotifywait` to watch `projects/` for new PDF files. When a PDF appears in `uploads/raw/`, extracts the project name from the directory path, and triggers `run_full_pipeline.sh`.

4. **`workflows/README.md`** — Documents: how to set up the watcher as a systemd service or cron job, how to run individual phases, how to configure the headless mode, environment variables needed.

---

## PHASE 10 — BUILD TEMPLATES

1. **`templates/quotation.html`** — Jinja2 template. Structure:
   - Header: CBC logo, Hamilton Parker Company, quote number, date, validity (30 days)
   - Customer info: GC name, project name, location
   - Line items grouped by door: Door #, size, items (frame, door, hardware set), qty, cost, margin, sale EA, ext price
   - Subtotal per door group
   - Separate restroom accessories block (partitions, grab bars, mirrors, dispensers, hand dryers)
   - FRP block (panels, trim, adhesive) if applicable
   - Freight line (TBD — usually omitted at estimate stage)
   - Grand total
   - Commercial terms: HP PO required, supply-only, sales tax per state rules
   - Footer: estimator name, contact

2. **`templates/quotation_email.md`** — Markdown email body template for routing to sales initiator. Fields: project name, quote attached, ready for review, key flags (low-confidence items, missing ratings).

3. **`templates/review_summary.html`** — Estimator review interface. Shows: all line items with confidence scores, color-coded flags (red = missing rating/low confidence, yellow = manual pricing needed, green = confident match), accept/edit/delete/add buttons (FR-9).

---

## PHASE 11 — BUILD UTILITY SCRIPTS

1. **`scripts/init_project.sh`** — Takes `<project_name>`, creates the full project directory tree under `projects/{name}/` with all subdirectories.

2. **`scripts/validate_project.py`** — Pre-flight checks: verifies all reference-library JSON files are present and valid, verifies price-book PDFs exist, verifies MCP servers are reachable, checks for stale price sheets.

3. **`scripts/export_audit_report.py`** — Reads `audit_trail.jsonl`, generates a human-readable HTML audit report showing: every tool call, timestamps, source pages referenced, cost sources used, confidence scores.

4. **`scripts/refresh_pricebooks.sh`** — Checks price-book PDF modification dates, compares against last-known dates, alerts if any are older than the defined refresh cadence.

---

## PHASE 12 — BUILD DOCUMENTATION

Write all 7 docs files in `docs/`:

1. **`architecture.md`** — System architecture: data flow diagram, MCP server contracts, agent interaction model, skill invocation chain, hook execution lifecycle.
2. **`cbc_process_flow.md`** — Phase 0→6 detailed process flow extracted from the requirements workbook Process Flow tab. Include system/tool and output for each phase.
3. **`requirements_matrix.md`** — FR-1 through FR-16 and NFR-1 through NFR-11 with status (Accurate/Pending/Out of scope).
4. **`guardrails.md`** — Mapping of each NFR to its enforcement mechanism (hook, rule, or both).
5. **`mcp_server_contracts.md`** — Tool schemas (input/output) for all 5 MCP servers.
6. **`headless_setup.md`** — How to configure `claude -p` / `--print` for background autopilot, systemd service setup, cron configuration, environment variables.
7. **`development_description.md`** — System overview, build phases, stakeholder notes (Kevin, Rick, Shanna), long-term engagement model.

---

## PHASE 13 — BUILD TESTS

1. **`tests/test_extraction.py`** — Runs `extract-door-schedule` skill against `1_Architectural.pdf`. Validates: door schedule found, at least 1 opening extracted, all openings have door_number and size, 4-digit notation correctly parsed, source_page populated for every opening.
2. **`tests/test_matching.py`** — Runs `match-hardware-sets` skill against extracted door schedule. Validates: every opening has a proposed match, confidence scores present (0.0-1.0), low-confidence matches flagged.
3. **`tests/test_pricing.py`** — Runs `price-line-item` and `apply-margin` skills. Validates: Sale EA = Cost / (1 - margin), Ext = Sale EA × Qty, subtotal = SUM(ext), grand total = SUM(subtotals). Margin within valid bands.
4. **`tests/test_guardrails/test_no_auto_send.sh`** — Verifies `pre_send_quote.sh` blocks `sendmail` command. Exit code 2 expected.
5. **`tests/test_guardrails/test_file_safety.sh`** — Verifies `pre_delete_guard.sh` blocks `rm -rf` outside projects/. Exit code 2 expected.

---

## PHASE 14 — BUILD SETTINGS.JSON AND GITIGNORE

### `.claude/settings.json`
Configure:
- All 5 MCP servers with `command: "python"` and `args: ["mcp-servers/{name}/server.py"]`
- All 5 hooks with correct matchers and event types (PreToolUse/PostToolUse)
- Permissions: allow Read/Write/Edit/Glob/Grep + all `mcp__*__*` tools
- Deny: `Bash(rm -rf *)`, `Bash(git push *)`, `Bash(sendmail *)`, `Bash(curl *mail*)`

### `.gitignore`
- `projects/*/uploads/raw/` (raw PDFs — large, not version controlled)
- `projects/*/uploads/processed/` (intermediate extraction artifacts)
- `.claude/settings.local.json` (secrets, P21 credentials)
- `__pycache__/`
- `*.pyc`
- `.venv/`
- `node_modules/`
- Keep: `projects/*/uploads/final/` (approved quotations ARE version controlled)
- Keep: `projects/*/audit_trail.jsonl` (audit trails ARE version controlled)

---

## PHASE 15 — COPY SAMPLE FILES AND FINAL VERIFICATION

1. Copy `1_Architectural.pdf` to `pricebooks/` NO — copy to `projects/dutch_bros_macarthur_2026/uploads/raw/1_Architectural.pdf` as the test fixture.
2. Copy `Hager-Price-Book-18-Complete-Effective-2-2-26_compressed-1.pdf` to `pricebooks/hager_price_book_18.pdf`.
3. Ensure `docs/CBC_Req_Validation_v1_3.xlsx` exists as reference.
4. Ensure `docs/architecture_source.md` exists (bootstrap architecture document).

### Final verification checklist:
- [ ] `find . -type f | wc -l` returns at least 60 files
- [ ] All `.sh` files in `.claude/hooks/` and `workflows/` are executable (`chmod +x`)
- [ ] All 9 agent files have valid YAML frontmatter (`name`, `description`, `model`)
- [ ] All 9 skill directories have a `SKILL.md` with valid YAML frontmatter
- [ ] All 8 rule files exist and are non-empty
- [ ] All 5 MCP server `server.py` files import `mcp` and define at least 2 tools
- [ ] `.claude/settings.json` is valid JSON with `mcpServers` and `hooks` keys
- [ ] `CLAUDE.md` exists, is under 200 lines, and references all 7 architecture layers
- [ ] `reference-library/` contains at least 10 JSON files
- [ ] `tests/` contains at least 5 test files
- [ ] `workflows/run_full_pipeline.sh` exists and is executable
- [ ] `projects/dutch_bros_macarthur_2026/uploads/raw/1_Architectural.pdf` exists
- [ ] `pricebooks/hager_price_book_18.pdf` exists

### After verification, output:
```
✅ CBC Estimating Copilot build complete.
   Files created: {count}
   Agents: 9
   Skills: 9
   Rules: 8
   Hooks: 5
   MCP Servers: 5
   Memory files: 13
   Reference JSON: {count}
   Test files: {count}
   
   To test: bash workflows/run_full_pipeline.sh dutch_bros_macarthur_2026
   To watch: bash workflows/watch_uploads.sh
```

---

## BUILD CONSTRAINTS

- Use Python 3.11+ for all MCP servers and scripts.
- Use the official `mcp` Python SDK (pip install mcp) for MCP servers with stdio transport.
- Use pdfplumber as the primary PDF text/table extraction library. Use PyMuPDF (fitz) for page image rendering. Use pytesseract for OCR fallback.
- Use Jinja2 for template rendering.
- Use rapidfuzz for fuzzy string matching (part numbers, product names).
- Every MCP tool that extracts data from a PDF MUST return `source_page` in its output (NFR-3 auditability).
- Every agent prompt MUST reference the relevant rules using `@.claude/rules/` imports.
- Every skill MUST have a `description` field in YAML frontmatter that clearly states when it should activate.
- No agent or skill may send emails, make HTTP POST requests to external services, or modify files outside `projects/{current_project}/`.
- The system MUST halt at Phase 6 with "Draft ready for estimator review" — never auto-send.
- All shell scripts must use `set -euo pipefail`.
- All Python files must have type hints on function signatures.
- All JSON output files must have a defined schema documented in the corresponding skill or agent file.
