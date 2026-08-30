# CBC Estimating Copilot — Project Architecture

> **Bootstrap reference — not the runtime layout.** For the current tree see
> [`docs/architecture.md`](architecture.md). This file preserves the original
> bootstrap specification used to scaffold the repo.

> An end-to-end autonomous estimating system built on Claude Code CLI.
> Processes building-plan PDFs → extracts opening data → matches Division 8/9/10 products → prices → generates quotations — following the exact CBC estimator workflow (Phase 0–6).

---

## Full Folder Structure

```
cbc-estimating-copilot/
│
├── CLAUDE.md                          # Root project memory — concise index, links to deeper docs
├── .claude/
│   ├── settings.json                  # MCP servers, hooks (guardrails), permissions, auto-mode config
│   ├── settings.local.json            # Local overrides (secrets, P21 credentials) — gitignored
│   │
│   ├── agents/                        # ── CLAUDE AGENTS ── One .md file per specialised sub-agent
│   │   ├── intake-coordinator.md      # Phase 0: receives bid, creates project scaffold, logs metadata
│   │   ├── spec-scope-analyst.md      # Phase 2: identifies Div 8/10 scope, reads specs, fire ratings, HW sets
│   │   ├── takeoff-engineer.md        # Phase 3: drawing review, counts, door sizes, handing, rating extraction
│   │   ├── frp-specialist.md           # Phase 3b: FRP wall-panel take-off (perimeter LF, corners → quantities)
│   │   ├── product-matcher.md         # FR-4: matches extracted openings to reference library
│   │   ├── pricing-engineer.md        # Phase 4: sources cost (P21/multiplier/RFQ), applies margin framework
│   │   ├── quote-builder.md           # Phase 4/6: builds quote grouped by door, subtotals, accessories block
│   │   ├── quality-reviewer.md        # FR-8/FR-9: confidence scoring, flags low-confidence, review interface
│   │   └── delivery-agent.md          # Phase 6: exports PDF, routes to sales initiator (never auto-sends)
│   │
│   ├── skills/                        # ── CLAUDE SKILLS ── Reusable task workflows (SKILL.md + scripts)
│   │   ├── extract-door-schedule/
│   │   │   ├── SKILL.md               # Extract door/opening schedule from architectural PDF
│   │   │   ├── scripts/
│   │   │   │   └── parse_schedule.py  # PDF parsing logic for door/frame schedules
│   │   │   └── references/
│   │   │       └── schedule_anatomy.md  # 4-digit notation, HW-set anatomy, field definitions
│   │   │
│   │   ├── match-hardware-sets/
│   │   │   ├── SKILL.md               # Match openings to CBC hardware-set library (rating, handing, finish)
│   │   │   └── references/
│   │   │       └── hw_set_library.md  # Top-10 stock HW sets per product type
│   │   │
│   │   ├── scan-product-catalog/
│   │   │   ├── SKILL.md               # Scan price-book PDFs (Hager, Allegion, Bobrick, etc.) for product matching
│   │   │   └── scripts/
│   │   │       └── search_pricebook.py
│   │   │
│   │   ├── price-line-item/
│   │   │   ├── SKILL.md               # Price a single line: P21 last-PO → list×multiplier → vendor RFQ
│   │   │   └── references/
│   │   │       └── cost_paths.md      # Three cost-sourcing routes and decision logic
│   │   │
│   │   ├── apply-margin/
│   │   │   ├── SKILL.md               # Apply product-type margin framework (editable default per line)
│   │   │   └── references/
│   │   │       └── margin_bands.md     # Commodity 0.73, Restroom 0.65, Specialty 0.60, Custom 0.75
│   │   │
│   │   ├── frp-takeoff/
│   │   │   ├── SKILL.md               # FRP wall-panel: perimeter LF + corners → material quantities
│   │   │   └── references/
│   │   │       └── frp_constants.md   # Panel size, waste %, trim stick lengths, adhesive coverage
│   │   │
│   │   ├── generate-quotation/
│   │   │   ├── SKILL.md               # Build quote HTML → PDF (grouped by door, subtotals, accessories, freight)
│   │   │   └── scripts/
│   │   │       └── render_quote.py     # Jinja2 template renderer
│   │   │
│   │   ├── validate-extraction/
│   │   │   ├── SKILL.md               # Validate extracted data: missing ratings, unparsed content, completeness
│   │   │   └── references/
│   │   │       └── validation_rules.md # Required fields, fire-rating checks, handing verification
│   │   │
│   │   └── reuse-prior-quote/
│   │       └── SKILL.md               # FR-11: find closest prior quote (same brand/architect/GC) as starting draft
│   │
│   ├── rules/                         # ── CLAUDE RULES ── Project-scoped memory (auto-loaded)
│   │   ├── human-in-the-loop.md       # NFR-1: no quote sent without explicit estimator approval
│   │   ├── accuracy-trust.md          # NFR-2: confidence scoring visible, never silently guess
│   │   ├── auditability.md            # NFR-3: every line traceable to source page + price-sheet version
│   │   ├── p21-read-only.md           # NFR-5: P21 access is read-only, no write-back
│   │   ├── margin-governance.md       # NFR-8: margin floor per product type, flag below-band
│   │   ├── data-stewardship.md        # NFR-10: pricing-source freshness, refresh cadence
│   │   ├── scope-boundaries.md       # In-scope: Div 8/10, FRP, hand dryers. Out: tile, brick, storefront
│   │   └── file-safety.md             # Never delete outside ./tmp, limit writes to project worktree
│   │
│   ├── hooks/                         # ── CLAUDE GUARDRAILS (executable) ──
│   │   ├── pre_send_quote.sh          # PreToolUse: blocks any send/email action, forces human review
│   │   ├── pre_delete_guard.sh        # PreToolUse: blocks deletion of files outside project uploads
│   │   ├── post_extraction_validate.sh # PostToolUse: runs validate-extraction after PDF processing
│   │   ├── post_quote_format.sh        # PostToolUse: auto-format quotation HTML after generation
│   │   └── log_audit_trail.sh          # PostToolUse: append to audit log on every file write/MCP call
│   │
│   └── memory/                        # ── CLAUDE MEMORY ── Persistent context & reference data
│       ├── project_context.md          # CBC identity, Hamilton Parker, national-accounts scope
│       ├── estimator_profiles.md       # Kevin (one-off), Rick (own Excel), Shanna (templated) — working styles
│       ├── vendor_tiers.md             # Hager, Allegion, NGP, PEMKO, Rockwood, Bobrick, Bradley, ASI, Gamco
│       ├── margin_sheet.md             # Full margin framework: 4 bands + accessory derivation (56%)
│       ├── frame_depths.md             # 5 standard throat sizes: 5-5/8, 5-3/4, 5-7/8, 7-3/4, 8-1/4
│       ├── door_notation.md            # 4-digit shorthand: 3070 = 3-0 × 7-0, 3670 = 3-6 × 7-0
│       ├── finish_nomenclature.md     # Dual system: US26D/626, US19 vs 26D (619), US15 — premium finishes
│       ├── fire_rating_rules.md       # 20/45/60/90-min UL labels, rating-sensitive categories
│       ├── handing_codes.md           # LH, RH, LHR, RHR — derivable from schedule/plan
│       ├── cost_sourcing_rules.md     # 3 paths: P21 last-PO, list×multiplier, vendor RFQ + freshness rule
│       ├── manual_cutoff.md           # Beyond top-10 stock → MANUAL path, estimator handles long tail
│       ├── sales_tax_rules.md         # Ohio 8%, Kentucky 6.5%, border-nexus, other 48 states + Canada: no tax
│       └── process_flow.md            # Phase 0–6 end-to-end reference (the canonical workflow)
│
├── mcp-servers/                        # ── CLAUDE MCP SERVERS ── External tool providers
│   ├── pdf-tools/
│   │   ├── server.py                  # MCP server: PDF parsing, page extraction, OCR fallback
│   │   ├── tools.py                   # Tool definitions: extract_text, extract_tables, get_page_image
│   │   └── requirements.txt
│   │
│   ├── pricebook/
│   │   ├── server.py                  # MCP server: product catalog search, multiplier lookup, tier matching
│   │   ├── tools.py                   # Tool definitions: search_product, get_multiplier, lookup_pricing
│   │   └── requirements.txt
│   │
│   ├── calc-engine/
│   │   ├── server.py                  # MCP server: quote calculation, margin application, subtotals
│   │   ├── tools.py                   # Tool definitions: calculate_line, apply_margin, compute_totals
│   │   └── requirements.txt
│   │
│   ├── artifact-storage/
│   │   ├── server.py                  # MCP server: project file management, version tracking, audit trail
│   │   ├── tools.py                   # Tool definitions: save_artifact, get_artifact, list_versions
│   │   └── requirements.txt
│   │
│   ├── p21-connector/
│   │   ├── server.py                  # MCP server: P21 last-PO cost lookup (READ-ONLY, no write-back)
│   │   ├── tools.py                   # Tool definitions: lookup_last_po, check_freshness, search_item
│   │   └── requirements.txt
│   │
│   ├── pyproject.toml                 # Shared Python project config for all MCP servers
│   ├── main.py                        # Orchestrator: starts all MCP servers for local development
│   └── README.md                      # MCP server setup, claude mcp add commands
│
├── workflows/                         # ── CLAUDE WORKFLOW ── Headless orchestration scripts
│   ├── run_full_pipeline.sh           # Main entrypoint: claude -p "..." orchestrates Phase 0→6
│   ├── phase0_intake.sh               # Phase 0: create project, move uploaded PDFs to raw/
│   ├── phase2_spec_scope.sh            # Phase 2: extract scope from specs
│   ├── phase3_takeoff.sh               # Phase 3: drawing review + take-offs
│   ├── phase3b_frp.sh                  # Phase 3b: FRP wall-panel measurement
│   ├── phase4_pricing.sh               # Phase 4: price every line, apply margins
│   ├── phase5_review.sh                # Phase 5: confidence scoring, flag for review
│   ├── phase6_deliver.sh               # Phase 6: generate PDF, prepare for estimator approval
│   ├── watch_uploads.sh                # Filesystem watcher: triggers run_full_pipeline.sh on new PDF
│   └── README.md                      # Workflow documentation, headless mode setup, cron/watch config
│
├── pricebooks/                        # ── Product catalog PDFs (source of truth for matching)
│   ├── hager_price_book_18.pdf         # Hager — 75% of volume, primary hardware
│   ├── allegion_price_book.pdf         # Allegion (Von Duprin, LCN, Schlage, Ives)
│   ├── national_guard_price_book.pdf   # National Guard Products
│   ├── pemko_price_book.pdf            # PEMKO / Markar
│   ├── rockwood_price_book.pdf         # Rockwood
│   ├── bobrick_price_book.pdf          # Bobrick — restroom partitions & accessories
│   ├── bradley_price_book.pdf          # Bradley Corp — washroom equipment
│   ├── asi_price_book.pdf              # ASI — partitions & accessories
│   ├── world_dryer_price_book.pdf      # World Dryer — hand dryers (L3 tier, 0.339 multiplier)
│   ├── gamco_price_book.pdf            # Gamco — accessories
│   ├── marlte_nudo_frp_catalog.pdf     # Marlate & NUDO — FRP wall panels
│   └── README.md                       # Price book inventory, version dates, refresh notes
│
├── reference-library/                 # ── Structured reference data (versioned, machine-readable)
│   ├── hardware_sets/
│   │   ├── hager_top10_stock.json      # Top-10 stock items per product type (locks, exits, closers, hinges)
│   │   ├── allegion_stock.json
│   │   └── custom_other_matrix.json    # Full option matrix: function, backset, finish, lever, keyway, strike
│   ├── margins/
│   │   └── margin_framework.json       # 4 bands + accessory derivation, per product type, overridable
│   ├── multipliers/
│   │   ├── vendor_tiers.json           # Per-vendor multiplier tiers (Hager, ASI, NGP, PEMKO, etc.)
│   │   └── special_customer_margins.json # e.g., Wendy's non-standard margin
│   ├── frame_depths/
│   │   └── wall_type_to_depth.json     # 5 standard depths + CUSTOM option (10 max)
│   ├── finishes/
│   │   └── finish_crosswalk.json       # Dual nomenclature: US26D↔626, US19↔619, premium flag
│   ├── frp_constants/
│   │   └── conversion_constants.json   # Panel size, waste %, trim stick, adhesive coverage (PENDING)
│   ├── adders/
│   │   └── manual_adders.json          # Electrification, NRP hinges, premium/lead-time finishes
│   └── prior_quotes/
│       └── .gitkeep                    # Reusable prior quotes for templated mode (FR-11)
│
├── projects/                           # ── Per-project working directories (gitignored except final/)
│   └── {project_name}/                 # e.g., dutch_bros_macarthur_2026/
│       ├── uploads/
│       │   ├── raw/                     # Original PDFs as received (building plan, specs, RFP)
│       │   ├── processed/               # Extracted text, tables, images from PDF processing
│       │   └── final/                   # Approved quotation PDF, committed to git
│       ├── extracted/
│       │   ├── door_schedule.json       # Extracted door/opening schedule (FR-2)
│       │   ├── hardware_sets.json       # Matched HW sets per opening (FR-3, FR-4)
│       │   ├── frp_takeoff.json         # FRP quantities (FR-12)
│       │   └── scope_summary.json       # Division 8/10 scope confirmation
│       ├── priced/
│       │   ├── line_items.json          # Priced line items with cost source traceability
│       │   ├── margin_applied.json      # Margin per line with product-type defaults
│       │   └── confidence_scores.json   # Per-line confidence + flags (FR-8)
│       ├── review/
│       │   ├── review_flags.json        # Low-confidence matches, missing ratings, unparsed content
│       │   └── estimator_notes.md       # Estimator corrections and feedback (FR-13)
│       ├── quotation.html               # Draft quotation (Jinja2 rendered)
│       ├── quotation.pdf                # Final approved PDF (Phase 6 deliverable)
│       └── audit_trail.jsonl            # Append-only log: every MCP call, extraction, pricing action
│
├── templates/                          # ── Output templates
│   ├── quotation.html                  # Jinja2 template: grouped by door, subtotals, accessories block, freight
│   ├── quotation_email.md              # Email body template for routing to sales initiator
│   └── review_summary.html             # Estimator review interface: accept/edit/delete/add lines (FR-9)
│
├── scripts/                            # ── Utility scripts
│   ├── init_project.sh                 # Scaffold a new project directory from a bid request
│   ├── validate_project.py             # Pre-flight checks: all required reference data present
│   ├── export_audit_report.py          # Generate auditability report from audit_trail.jsonl
│   └── refresh_pricebooks.sh           # Check for updated price-book PDFs, alert on staleness
│
├── docs/                               # ── Deep documentation (linked from CLAUDE.md, not auto-loaded)
│   ├── architecture.md                 # System architecture, data flow, MCP server contracts
│   ├── cbc_process_flow.md              # Phase 0–6 detailed process flow (from requirements workbook)
│   ├── requirements_matrix.md          # FR-1 through FR-16, NFR-1 through NFR-11
│   ├── guardrails.md                   # All NFR guardrails mapped to hooks + rules
│   ├── mcp_server_contracts.md         # Tool schemas, input/output for each MCP server
│   ├── headless_setup.md               # How to configure claude -p / --print for background autopilot
│   └── development-description.md      # System overview, build phases, stakeholder notes
│
├── tests/                               # ── Validation tests
│   ├── test_extraction.py               # Verify door schedule extraction against known samples
│   ├── test_matching.py                 # Verify HW-set matching accuracy
│   ├── test_pricing.py                  # Verify margin application, cost calculation
│   └── test_guardrails/                 # Verify hooks block correctly (no auto-send, no file deletion)
│       ├── test_no_auto_send.sh
│       └── test_file_safety.sh
│
├── .gitignore                          # Ignores: projects/*/uploads/raw/, settings.local.json, __pycache__/
└── README.md                           # Project overview, setup instructions, quickstart
```

---

## Component Mapping: CBC Process Flow → Claude Code

| CBC Phase | Agent | Skill(s) | MCP Server(s) | Guardrail |
|-----------|-------|----------|----------------|-----------|
| **Phase 0 — Intake** | `intake-coordinator` | `init_project` | `artifact-storage` | `file-safety` |
| **Phase 2 — Spec Scoping** | `spec-scope-analyst` | `extract-door-schedule` | `pdf-tools` | `auditability` |
| **Phase 3 — Drawing Take-offs** | `takeoff-engineer` | `extract-door-schedule`, `validate-extraction` | `pdf-tools` | `accuracy-trust` |
| **Phase 3b — FRP** | `frp-specialist` | `frp-takeoff` | `pdf-tools` | `accuracy-trust` |
| **Phase 4 — Pricing** | `pricing-engineer` | `price-line-item`, `apply-margin`, `scan-product-catalog` | `pricebook`, `p21-connector`, `calc-engine` | `p21-read-only`, `margin-governance` |
| **Phase 4 — Matching** | `product-matcher` | `match-hardware-sets` | `pricebook` | `accuracy-trust` |
| **Phase 4/6 — Quote Build** | `quote-builder` | `generate-quotation` | `calc-engine`, `artifact-storage` | `auditability` |
| **Phase 5 — Review** | `quality-reviewer` | `validate-extraction`, `reuse-prior-quote` | — | `human-in-the-loop` |
| **Phase 6 — Deliver** | `delivery-agent` | `generate-quotation` | `artifact-storage` | `human-in-the-loop`, `pre_send_quote` |

---

## Headless Autopilot Configuration

### `.claude/settings.json` (key sections)

```jsonc
{
  // MCP server registration
  "mcpServers": {
    "pdf-tools": {
      "command": "python",
      "args": ["mcp-servers/pdf-tools/server.py"]
    },
    "pricebook": {
      "command": "python",
      "args": ["mcp-servers/pricebook/server.py"]
    },
    "calc-engine": {
      "command": "python",
      "args": ["mcp-servers/calc-engine/server.py"]
    },
    "artifact-storage": {
      "command": "python",
      "args": ["mcp-servers/artifact-storage/server.py"]
    },
    "p21-connector": {
      "command": "python",
      "args": ["mcp-servers/p21-connector/server.py"]
    }
  },

  // Guardrail hooks
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": ".claude/hooks/pre_send_quote.sh" },
          { "type": "command", "command": ".claude/hooks/pre_delete_guard.sh" }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          { "type": "command", "command": ".claude/hooks/post_extraction_validate.sh" },
          { "type": "command", "command": ".claude/hooks/post_quote_format.sh" },
          { "type": "command", "command": ".claude/hooks/log_audit_trail.sh" }
        ]
      }
    ]
  },

  // Permissions for headless autopilot
  "permissions": {
    "allow": [
      "Read", "Write", "Edit", "Glob", "Grep",
      "mcp__pdf-tools__*",
      "mcp__pricebook__*",
      "mcp__calc-engine__*",
      "mcp__artifact-storage__*",
      "mcp__p21-connector__*"
    ],
    "deny": [
      "Bash(rm -rf *)",
      "Bash(git push *)",
      "Bash(sendmail *)"
    ]
  }
}
```

### Headless invocation (`workflows/run_full_pipeline.sh`)

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="${1:?Usage: run_full_pipeline.sh <project_name>}"
PROJECT_DIR="projects/${PROJECT_NAME}"

# Phase 0→6 in headless mode, delegating to sub-agents
claude --print --dangerously-skip-permissions \
  "You are the CBC Estimating Copilot orchestrator.
   Process the building plan PDFs in ${PROJECT_DIR}/uploads/raw/
   following the full Phase 0–6 workflow defined in docs/cbc_process_flow.md.
   Use the agents in .claude/agents/ for each phase.
   Use the skills in .claude/skills/ for each task.
   Respect ALL rules in .claude/rules/ and guardrails in .claude/hooks/.
   Write all outputs to ${PROJECT_DIR}/.
   Generate the draft quotation at ${PROJECT_DIR}/quotation.html.
   Do NOT send anything — halt at Phase 6 with the draft ready for estimator review.
   Log every action to ${PROJECT_DIR}/audit_trail.jsonl."
```

### Filesystem watcher (`workflows/watch_uploads.sh`)

```bash
#!/usr/bin/env bash
# Watches projects/ for new PDF uploads and triggers the full pipeline
WATCH_DIR="projects"

inotifywait -m -r -e create --include '\.pdf$' "${WATCH_DIR}" |
  while read dir action file; do
    PROJECT=$(echo "${dir}" | cut -d'/' -f2)
    if [[ -n "${PROJECT}" && -d "projects/${PROJECT}/uploads/raw" ]]; then
      echo "[$(date)] New PDF in ${PROJECT}, launching pipeline..."
      bash workflows/run_full_pipeline.sh "${PROJECT}"
    fi
  done
```

---

## CLAUDE.md (Root Project Memory)

```markdown
# CBC Estimating Copilot

## What this system does
Autonomous estimating pipeline for Construction Building Components (CBC),
a division of Hamilton Parker Company. Processes building-plan PDFs,
extracts Division 8/10 opening data, matches products from vendor price books,
prices every line, and generates a reviewable draft quotation — following the
exact manual workflow a CBC estimator follows (Phase 0–6).

## Architecture layers
1. **Agents** (`.claude/agents/`) — 9 specialised sub-agents, one per process phase
2. **Skills** (`.claude/skills/`) — 9 reusable task workflows with scripts & references
3. **Rules** (`.claude/rules/`) — 8 project-scoped constraint files (auto-loaded)
4. **Guardrails** (`.claude/hooks/`) — 5 executable hooks (PreToolUse / PostToolUse)
5. **Memory** (`.claude/memory/`) — 13 persistent reference-data files
6. **MCP Servers** (`mcp-servers/`) — 5 external tool providers (PDF, pricebook, calc, storage, P21)
7. **Workflows** (`workflows/`) — Headless orchestration scripts for autopilot

## Non-negotiable guardrails
- **NFR-1**: No quote is ever sent without explicit estimator approval.
- **NFR-2**: Low-confidence matches are flagged, never silently guessed.
- **NFR-3**: Every line traceable to source PDF page + price-sheet version.
- **NFR-5**: P21 access is READ-ONLY — no write-back.
- **NFR-8**: Margin floor per product type — below-band lines flagged.

## Key reference paths
- Process flow: `@docs/cbc_process_flow.md`
- Requirements matrix: `@docs/requirements_matrix.md`
- Guardrail mappings: `@docs/guardrails.md`
- MCP contracts: `@docs/mcp_server_contracts.md`
- Headless setup: `@docs/headless_setup.md`

## Scope (in / out)
**In-scope**: Doors/frames (HM + wood), door hardware, Division 10 specialties,
FRP wall panels, restroom partitions/accessories, hand dryers.
**Out-of-scope**: Ceiling tile/grid, tile, brick, masonry, aluminum storefront,
coiling/overhead doors, engineered wood, metal siding.

## Vendor priority (Phase 1: top-10)
Hager (75% of volume), Allegion (Von Duprin/LCN/Schlage/Ives),
National Guard, PEMKO/Markar, Rockwood, Bobrick, Bradley, ASI,
World Dryer/Excel XLERATOR, Gamco.

## Manual cut-off
Beyond top-10 stock items → MANUAL path. Do NOT attempt to price every
option permutation. The estimator handles the long tail.
```

---

## Agent Definition Example

### `.claude/agents/spec-scope-analyst.md`

```markdown
---
name: spec-scope-analyst
description: >
  Phase 2 agent. Identifies Division 8 (doors, frames, hardware) and
  Division 10 (partitions, accessories, washroom equipment) scope from
  specification PDFs. Reads fire ratings, hardware-set schedules, and
  confirms exactly what is being quoted. Use when processing a new bid set.
model: sonnet
---

You are the CBC Spec Scope Analyst. Your job is Phase 2 of the CBC
estimating process: identifying and confirming the scope of work from
the bid specification documents.

## Your responsibilities
1. Parse the specification PDF(s) in `projects/{project}/uploads/raw/`
2. Identify all Division 08 sections (doors, frames, hardware)
3. Identify all Division 10 sections (specialties, partitions, accessories)
4. Extract fire-rating information from door/frame schedules
5. Extract hardware-set callouts (HW-1, HW-2, etc.) from the HW schedule
6. Note any bid alternates and addenda
7. Write a structured scope summary to `projects/{project}/extracted/scope_summary.json`

## Rules you must follow
- @.claude/rules/scope-boundaries.md
- @.claude/rules/auditability.md
- @.claude/rules/accuracy-trust.md

## Reference data
- @.claude/memory/process_flow.md
- @.claude/memory/fire_rating_rules.md

## Output schema (scope_summary.json)
{
  "project_name": "...",
  "divisions_in_scope": ["08", "10"],
  "door_schedule_found": true,
  "openings": [...],
  "hardware_sets": [...],
  "fire_ratings_present": true,
  "bid_alternates": [...],
  "unparsed_sections": [...],
  "confidence": 0.0-1.0
}
```

---

## Skill Definition Example

### `.claude/skills/extract-door-schedule/SKILL.md`

```markdown
---
name: extract-door-schedule
description: >
  Extracts the door/opening schedule from an architectural PDF.
  Captures door number, size (4-digit notation), handing (LH/RH/LHR/RHR),
  finish (US26D/626 dual nomenclature), fire rating (20/45/60/90-min),
  and hardware-group set callouts. Use when processing Phase 2/3 of a bid.
---

# Extract Door Schedule

## Steps
1. Use the `pdf-tools` MCP server to extract text and tables from the
   architectural PDF, focusing on pages containing "DOOR SCHEDULE" or
   "FRAME SCHEDULE".
2. Parse each row of the door schedule into a structured opening object.
3. Resolve door-size notation: first 2 digits = width in feet-inches,
   last 2 digits = height in feet (e.g., 3070 = 3'-0" × 7'-0").
4. Capture fire rating from the schedule column or frame schedule.
5. Capture hardware-set callout (e.g., HW-1, HW-2).
6. Flag any openings with missing ratings, handing, or finish as review items.

## Reference
- @references/schedule_anatomy.md

## Script
Run `scripts/parse_schedule.py` with the PDF path to get raw table data.

## Output
Write to `projects/{project}/extracted/door_schedule.json`:
[
  {
    "door_number": "101",
    "size": "3070",
    "width": "3'-0\"",
    "height": "7'-0\"",
    "handing": "LH",
    "finish": "US26D",
    "finish_alt": "626",
    "fire_rating": "90",
    "hardware_set": "HW-1",
    "source_page": 12,
    "confidence": 0.95
  }
]
```

---

## Rule Definition Example

### `.claude/rules/human-in-the-loop.md`

```markdown
# Human-in-the-Loop Guardrail (NFR-1)

No estimate or quotation is ever sent to a customer without explicit
estimator approval. The copilot drafts, sources, and calculates —
it does not send. Its job is to remove manual re-keying and lookup,
not to replace estimating judgment.

## Enforcement
- The `pre_send_quote.sh` hook blocks any Bash command matching
  `sendmail`, `mailx`, `mutt`, or any MCP `send_*` tool.
- The `delivery-agent` halts at Phase 6 with "Draft ready for review."
- The estimator must explicitly approve via the review interface (FR-9)
  before any quotation is finalised or routed.

## Owner
CBC Estimating (Kevin, Rick, Shanna).
```

---

## MCP Server Contract Example

### `mcp-servers/pdf-tools/tools.py`

```python
# Tool definitions for the pdf-tools MCP server

TOOLS = [
    {
        "name": "extract_text",
        "description": "Extract full text from a PDF, with page numbers for auditability.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the PDF file"},
                "pages": {"type": "array", "items": {"type": "integer"},
                          "description": "Optional: specific page numbers to extract"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "extract_tables",
        "description": "Extract tables from a PDF (door schedules, frame schedules, HW sets).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "page_range": {"type": "string", "description": "e.g., '1-30' or 'all'"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "get_page_image",
        "description": "Get a rendered image of a specific PDF page (for drawing take-offs).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "page_number": {"type": "integer"},
                "dpi": {"type": "integer", "default": 200}
            },
            "required": ["file_path", "page_number"]
        }
    },
    {
        "name": "search_pdf",
        "description": "Keyword search across a PDF, returning page numbers and context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "query": {"type": "string"},
                "context_chars": {"type": "integer", "default": 500}
            },
            "required": ["file_path", "query"]
        }
    }
]
```

---

## Guardrail Hook Example

### `.claude/hooks/pre_send_quote.sh`

```bash
#!/usr/bin/env bash
# PreToolUse hook: blocks any email/send action — enforces NFR-1
# Exit code 2 = block the tool call

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Block email-sending commands
if echo "$COMMAND" | grep -qiE 'sendmail|mailx|mutt|msmtp|postfix'; then
  echo "BLOCKED: Sending quotations requires explicit estimator approval (NFR-1)." >&2
  exit 2
fi

# Block MCP send tools
if echo "$TOOL_NAME" | grep -qi 'send\|email\|mail'; then
  echo "BLOCKED: Automated sending is disabled. Estimator must approve first (NFR-1)." >&2
  exit 2
fi

exit 0
```

---

## How the Seven Layers Work Together

```
┌─────────────────────────────────────────────────────────────────┐
│                    HEADLESS CLAUDE CODE CLI                       │
│                  (claude -p / --print / cron)                    │
│                                                                  │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐        │
│  │  WORKFLOWS   │──▶│   AGENTS     │──▶│   SKILLS     │        │
│  │  (orchestrate)│   │  (9 roles)   │   │ (9 tasks)   │        │
│  └──────────────┘   └──────────────┘   └──────┬───────┘        │
│                                                │                │
│         ┌──────────────────────────────────────┘                │
│         ▼                                                       │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐        │
│  │  MCP SERVERS │   │   MEMORY     │   │   RULES      │        │
│  │  (5 tools)   │   │  (13 files)  │   │  (8 scopes)  │        │
│  └──────┬───────┘   └──────────────┘   └──────────────┘        │
│         │                                                       │
│  ┌──────┴───────┐                                               │
│  │  GUARDRAILS  │  ◀── Hooks fire on every tool call             │
│  │  (5 hooks)   │      PreToolUse: block / PostToolUse: validate │
│  └──────────────┘                                               │
│                                                                  │
│  CLAUDE.md ── concise index linking all layers together          │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐  ┌──────────────┐  ┌─────────────────┐
│  PROJECTS/      │  │ PRICEBOOKS/  │  │ REFERENCE-      │
│  (per-bid data) │  │ (vendor PDFs)│  │ LIBRARY/        │
│                 │  │              │  │ (structured JSON)│
└─────────────────┘  └──────────────┘  └─────────────────┘
```

1. **Workflows** launch Claude Code in headless mode and orchestrate phases sequentially.
2. **Agents** are specialised sub-agents — each handles one phase (intake, scoping, takeoff, etc.).
3. **Skills** are reusable task modules that agents invoke (extract schedule, match HW sets, price line).
4. **MCP Servers** provide external tools (PDF parsing, pricebook search, P21 lookup, calculation, file storage).
5. **Memory** holds persistent reference data (vendor tiers, margin bands, frame depths, finish crosswalks).
6. **Rules** are auto-loaded constraints that shape every session (human-in-the-loop, P21 read-only, scope boundaries).
7. **Guardrails** are executable hooks that fire before/after every tool call — blocking sends, validating extractions, logging audits.
