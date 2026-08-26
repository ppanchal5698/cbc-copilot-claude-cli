# CBC Estimating Copilot

Autonomous estimating pipeline for **Construction Building Components (CBC)**, the
national-accounts division of The Hamilton Parker Company.

It reads building-plan PDFs, extracts Division 8/10 opening data, matches products
against 26 real vendor price books, prices every line, and produces a reviewable
**draft** quotation - following the exact Phase 0-6 workflow a CBC estimator
follows today.

> The estimator stays in control of every quote. The copilot drafts, sources and
> calculates - **it does not send**.

## Quickstart

```bash
python -m pip install -e mcp-servers
```

```bash
python mcp-servers/main.py --selftest
```

```bash
bash scripts/init_project.sh dutch_bros_macarthur_2026 building-plans/1_Architectural.pdf
```

```bash
bash workflows/run_full_pipeline.sh dutch_bros_macarthur_2026
```

The run ends with `quotation.html`, a review summary, an audit trail, and the
message **"Draft ready for estimator review"**.

## What is here

| Path | Contents |
|---|---|
| `CLAUDE.md` | Project index - the guardrails and scope in under 200 lines |
| `.claude/agents/` | 9 sub-agents, one per process phase |
| `.claude/skills/` | 9 task workflows with scripts and references |
| `.claude/rules/` | 8 auto-loaded constraints |
| `.claude/hooks/` | 5 executable guardrails (Python) |
| `.claude/memory/` | 13 business-rule and reference files |
| `mcp-servers/` | 5 stdio MCP servers - pdf, pricebook, calc, storage, P21 |
| `workflows/` | Headless orchestration - full pipeline, per-phase, watcher |
| `pricebooks/` | 26 vendor price books across 10 vendors, read-only |
| `reference-library/` | 10 structured JSON files - margins, multipliers, finishes, frame depths, adders |
| `templates/` | Quotation, review interface, email draft |
| `scripts/` | init, pre-flight validation, audit report, price-book staleness |
| `docs/` | Architecture, process flow, requirements matrix, guardrails, MCP contracts, headless setup |
| `tests/` | 48 pytest checks plus 23 guardrail checks |
| `projects/` | Per-bid working directories |

## The pipeline

```
uploads/raw/*.pdf
  → intake-coordinator    scope_metadata.json
  → spec-scope-analyst    scope_summary.json
  → takeoff-engineer      door_schedule.json
  → frp-specialist        frp_takeoff.json
  → product-matcher       hardware_sets.json
  → pricing-engineer      line_items.json, margin_applied.json
  → quote-builder         quotation.html
  → quality-reviewer      review_flags.json, review_summary.html
  → delivery-agent        quotation.pdf, uploads/final/
  → HALT
```

## The five guarantees

| | |
|---|---|
| **NFR-1** | No quote is sent without explicit estimator approval |
| **NFR-2** | Low-confidence matches are flagged, never silently guessed |
| **NFR-3** | Every line traces to a source PDF page and a price-sheet version |
| **NFR-5** | P21 access is read-only - the connector exposes no write tools |
| **NFR-8** | Below-band margins are flagged (approval routing deferred) |

Verify the two that are enforced by hooks:

```bash
bash tests/test_guardrails/test_no_auto_send.sh && bash tests/test_guardrails/test_file_safety.sh
```

## Scope

**In:** metal and wood doors · HM frames (welded and knock-down) · HP-Fabrication
doors · door hardware · Division 10 specialties · restroom partitions and
accessories · hand dryers · FRP wall panels.

**Out:** ceiling tile and grid · tile · thin brick · masonry · aluminum/glass
storefront · coiling, overhead and oversized doors · engineered wood · metal
siding · JL Industries · **Scranton** (access lost) · **American Dryer** (not used).

## Vendors - Phase 1 top-10

Hager (~75% of volume) · Allegion via Banner/SecLock, manual pricing · National
Guard · PEMKO/Markar · Rockwood · Bobrick · Bradley · ASI · World Dryer and Excel
XLERATOR · Gamco. FRP: Marlite / NUDO / Midwest-East Coast.

Beyond the top-10 stock items there is a hard **MANUAL cut-off** (NR-13). The
system does not attempt to price every option permutation - the estimator handles
the long tail. Expect a real bid to route a meaningful share of lines to manual;
that is the design working.

## Known gaps - by design, not oversight

| Gap | Behaviour today |
|---|---|
| Fire-rating rules (Matrix 7.3) | Extracted where present, **flagged at severity high** where absent. Never inferred |
| FRP conversion constants (Open Item 5) | Geometry captured, quantities `null`, `blocked_on` recorded |
| Alternates and addenda (Matrix 4.1) | Base and alternates kept as distinct groups; no reconciliation logic |
| Top-10 stock list (NR-6) | Draft harvested from the Hager price book, marked PENDING |
| P21 integration (NR-10) | Connector returns a structured "manual entry required" response |
| Data stewardship (NFR-10) | Staleness reported on every pre-flight; no owner assigned |

## Tests

```bash
python -m pytest tests/ -q
```

```bash
python scripts/validate_project.py --all
```

Extraction tests run against the real Dutch Bros bid set, not a synthetic sample.

## Documentation

- [Architecture](docs/architecture.md)
- [CBC process flow](docs/cbc_process_flow.md)
- [Requirements matrix](docs/requirements_matrix.md)
- [Guardrails](docs/guardrails.md)
- [MCP server contracts](docs/mcp_server_contracts.md)
- [Headless setup](docs/headless_setup.md)
- [Development description](docs/development-description.md)
