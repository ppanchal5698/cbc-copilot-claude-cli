# CBC Estimating Copilot

## What this system does
Autonomous estimating pipeline for Construction Building Components (CBC), the
national-accounts division of The Hamilton Parker Company. It processes building-plan
PDFs, extracts Division 8/10 opening data, matches products against vendor price books,
prices every line, and generates a reviewable **draft** quotation — following the exact
manual workflow a CBC estimator follows (Phase 0–6). It drafts, sources, and calculates.
**It does not send.**

## Architecture layers
1. **Agents** (`.claude/agents/`) — 9 sub-agents, one per process phase
2. **Skills** (`.claude/skills/`) — 9 reusable task workflows with scripts & references
3. **Rules** (`.claude/rules/`) — 8 project-scoped constraint files
4. **Guardrails** (`.claude/hooks/`) — 5 executable hooks (PreToolUse / PostToolUse)
5. **Memory** (`.claude/memory/`) — 13 persistent reference-data files
6. **MCP Servers** (`mcp-servers/`) — 5 tool providers (pdf, pricebook, calc, storage, P21)
7. **Workflows** (`workflows/`) — headless orchestration scripts for autopilot

## Non-negotiable guardrails
- **NFR-1** — No quote is ever sent without explicit estimator approval.
- **NFR-2** — Low-confidence matches are flagged, never silently guessed.
- **NFR-3** — Every line traces to a source PDF page and a price-sheet version + effective date.
- **NFR-5** — P21 access is READ-ONLY; no write-back.
- **NFR-8** — Margin floor per product type; below-band lines are flagged (governance deferred).

## Key reference paths
- Process flow: @docs/cbc_process_flow.md
- Requirements matrix: @docs/requirements_matrix.md
- Guardrail mappings: @docs/guardrails.md
- MCP contracts: @docs/mcp_server_contracts.md
- Headless setup: @docs/headless_setup.md
- Architecture: @docs/architecture.md

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

## The pipeline halts at Phase 6
Every run ends with `quotation.html` written and the message
**"Draft ready for estimator review"**. Nothing is emailed, posted, or transmitted.
