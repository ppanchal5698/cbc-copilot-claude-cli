# CBC Estimating Copilot

## What this system does
Autonomous estimating pipeline for Construction Building Components (CBC), the
national-accounts division of The Hamilton Parker Company. It processes building-plan
PDFs, extracts Division 8/10 opening data, matches products against vendor price books,
prices every line, and generates a reviewable **draft** quotation — following the exact
manual workflow a CBC estimator follows (Phase 0–6). It drafts, sources, and calculates.
**It does not send.**

## Architecture layers
1. **Agents** (`.claude/agents/`) — 10 sub-agents, one per process phase
2. **Skills** (`.claude/skills/`) — 9 reusable task workflows with scripts & references
3. **Rules** (`.claude/rules/`) — 8 project-scoped constraint files
4. **Guardrails** (`.claude/hooks/`) — 5 executable hooks (PreToolUse / PostToolUse)
5. **Memory** (`.claude/memory/`) — 13 persistent reference-data files
6. **MCP Servers** (`mcp-servers/`) — 6 tool providers (pdf, catalog, calc, storage, P21, document-index),
   registered in **`.mcp.json`** at the repo root. `.claude/settings.json` has no
   `mcpServers` key — a block there is ignored, and the run silently gets no tools.
7. **Workflows** (`workflows/`) — headless orchestration scripts for autopilot

## The Ops-Hub application
The estimator drives the pipeline through a web app; Claude Code works behind it.

- **`web/`** — Next.js 15 UI (dashboard, bid board, the four bid stages, catalog, price books)
- **`apps/api/`** — FastAPI: routing, request/response, auth. The web layer, and only that.
- **`apps/worker/`** — claims queued jobs and runs `claude --print`, then syncs what
  Claude wrote on disk into MongoDB.
- **`src/cbc/`** — the domain, and the one thing both applications import.
  Configuration, the Mongo handle, the schemas and every business rule live here,
  so neither application depends on the other. That edge used to exist: `api`
  owned the rules, so `worker` had to import the web application to reach them.
  - `cbc/config.py`, `cbc/db.py`, `cbc/schemas/`, `cbc/services/` — the rules.
    Quote arithmetic is delegated to `cbc/core/calc.py`, so the numbers have one
    implementation.
  - `cbc/core/` — the pure kernel: the money math, the PDF page operations,
    credential redaction, and the one place that spawns the CLI. It imports
    nothing above it. The `calc-engine` and `pdf-tools` MCP servers are adapters
    over these same modules, so a price a run computes and a price the API
    computes cannot drift.
  - `cbc/catalog/` — the product search index. The vendor sheets under the
    `pricebooks` directory are the source of truth; this keeps a **rebuildable**
    SQLite FTS5 index of what is in them, so a search costs a fraction of a
    millisecond instead of re-reading 1 391 pages. Uploading a sheet queues
    `index_catalog`; deleting one queues `delete_catalog` and the cascade removes
    its search records. There is no product table to maintain by hand —
    `python -m cbc.catalog.rebuild` reconstructs the lot. The index lives on a
    **named volume**, never a bind mount: SQLite needs dependable locking and WAL
    needs shared memory, and `/app/projects` is 9p.
  - `cbc/documents/` — LLM deep indexing for large, messy PDFs, with versioning
    and diffing. `cbc/core/pdfrows` is shared with `cbc/catalog` so a price book
    and a bid set cannot disagree about what a page says.

**The dependency rule, in one line:** `apps/*` imports `cbc`; `cbc` imports neither
application. `tests/api/test_layering.py` asserts it, and walks function-level
imports too — that is the shape a cycle takes when nobody wants to admit to one.
- **MongoDB** — the system of record between the two actors. PDFs stay on the
  filesystem under `projects/{slug}/uploads/raw/`, which is what the skills expect.

- **Containers** — `docker compose up -d --build` runs all five. `api` and
  `worker` share one image; it runs as a **non-root** user because Claude Code
  refuses `--dangerously-skip-permissions` under root, and its entrypoint marks
  `/app` trusted because an untrusted workspace silently denies every MCP call.
- **Provider** — which Claude Code runs the passes is configured on the settings
  screen and resolved in one place, `src/cbc/services/provider.py`. The environment
  wins over the database, so Secrets Manager stays authoritative in production.

Setup and the job flow: `docs/opshub_setup.md`

**Every user action that needs machine work becomes a job**, never a direct spawn:
`extract_bid_set`, `rerun_extraction`, `match_and_price`, `build_proposal`,
`ingest_pricebook`, `ingest_addendum`. At each phase boundary the estimator's confirmed state is
written back down to `extracted/` and `priced/` so Claude's next pass reconciles
against it rather than overwriting it.

## Non-negotiable guardrails
- **NFR-1** — No quote is ever sent without explicit estimator approval.
- **NFR-2** — Low-confidence matches are flagged, never silently guessed.
- **NFR-3** — Every line traces to a source PDF page and a price-sheet version + effective date.
- **NFR-5** — P21 access is READ-ONLY; no write-back.
- **NFR-8** — Margin floor per product type; below-band lines are flagged (governance deferred).

## Key reference paths

`@` inlines a file into every session, on every turn. Only the process flow earns
that: it is the thing a run is actually following. The rest are here as paths, to
be read when a question needs them.

Inlining all of these cost ~18,000 tokens of context before a single sheet was
read - and `opshub_setup.md`, 13 KB about Docker ports and web-app
troubleshooting, was inlined twice.

- Process flow (Phase 0-6): @docs/cbc_process_flow.md
- Guardrail mappings: `docs/guardrails.md`
- Requirements matrix: `docs/requirements_matrix.md`
- MCP contracts: `docs/mcp_server_contracts.md` (the tool schemas are already in
  context from the servers themselves; this is the prose version)
- Headless setup: `docs/headless_setup.md`
- Architecture: `docs/architecture.md`
- Ops-Hub setup: `docs/opshub_setup.md`

## Scope
**In-scope**: metal & wood doors; HM frames (welded/loaded & knock-down); HP-Fabrication
doors; door hardware; Division 10 specialties; restroom partitions & accessories; washroom
equipment / hand dryers; FRP wall panels.

**Out-of-scope**: ceiling tile & grid, tile, thin brick, masonry (other HP departments);
aluminum/glass storefront; coiling/overhead/oversized doors; engineered wood; metal siding /
extruded aluminum; JL Industries access doors; **Scranton** (access lost); American Dryer
(no longer used).

## Vendor priority (Phase 1: top-10 only, ~90%+ of quotes)
Hager (~75% of volume) · Allegion (Von Duprin / LCN / Schlage / Ives — bought via Banner
Solutions or SecLock, so **manual price entry**) · National Guard Products · PEMKO / Markar ·
Rockwood · Bobrick · Bradley · ASI · World Dryer + Excel XLERATOR · Gamco.
FRP: Marlite / NUDO / Midwest–East Coast.

## Manual cut-off (NR-13)
Automate the stock / top-N items only. Beyond that there is a hard **MANUAL** cut-off:
custom sizes (e.g. 9-ft doors), unusual preps, options not sold in years, distributor-bought
lines. Do **not** attempt to price every option permutation — the estimator handles the long
tail. See @.claude/memory/manual_cutoff.md.

## Alternates and addenda (FR-14) — interim only
The base bid and each alternate are **distinct, comparable line groups**, and an
addendum **snapshots** prior work rather than overwriting it — differences are
flagged, never merged. How a reconciliation resolves is still open (Matrix 4.1 /
Open Item 11), and every response and screen says so.

## The pipeline halts at Phase 6
Every run ends with `quotation.html` written and the message
**"Draft ready for estimator review"**. Nothing is emailed, posted, or transmitted.
