# CBC Estimating Copilot — Remediation Plan

**Audit date:** 2026-09-01  
**Source:** [CODEBASE_AUDIT_REPORT.md](./CODEBASE_AUDIT_REPORT.md)

Phased implementation plan. Each task includes ID, priority, components, dependencies, steps, outcome, regression risk, and validation criteria.

---

## Phase 0 — Safety and Backup

### R0-001: Establish audit baseline

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Components** | CI, git |
| **Dependencies** | None |
| **Steps** | 1. Tag current commit as `audit-baseline-2026-09-01`. 2. Confirm CI green: 464 pytest, MCP selftest, web typecheck/test/build. |
| **Outcome** | Rollback point before remediation |
| **Regression Risk** | None |
| **Validation** | `git tag`; CI passes |

### R0-002: Document accepted security posture

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Components** | `docs/guardrails.md`, ops runbook |
| **Dependencies** | None |
| **Steps** | Document that `--dangerously-skip-permissions` is required for unattended runs; enumerate hook enforcement; define network isolation requirements for API |
| **Outcome** | Operators understand security model |
| **Regression Risk** | None |
| **Validation** | Ops doc reviewed |

---

## Phase 1 — Critical Production Failures

### R1-001: Remove dead job types

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Components** | `src/cbc/schemas/common.py`, `web/lib/job-error.ts`, `scripts/validate_project.py` |
| **Dependencies** | R0-001 |
| **Steps** | 1. Remove `index_document`, `delete_document` from JobType literal. 2. Remove UI labels from `job-error.ts`. 3. Remove from validator job set. 4. Grep for remaining references. |
| **Outcome** | No enqueueable job types without handlers |
| **Regression Risk** | Low — types never successfully ran |
| **Validation** | `pytest tests`; grep returns zero matches |

### R1-002: Fix `rerun_extraction` prompt

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Components** | `apps/worker/prompts.py` |
| **Dependencies** | None |
| **Steps** | 1. Add takeoff-engineer phase to RERUN template. 2. Reference `.claude/agents/takeoff-engineer.md` in solo path. 3. Specify `extracted/door_schedule.json` output. 4. Include reconcile-against-confirmed-lines instruction. |
| **Outcome** | Rerun extraction produces valid artifacts |
| **Regression Risk** | Medium — changes run behavior |
| **Validation** | Render prompt via `python -m apps.worker.prompts`; rerun on test project |

### R1-003: Fix PREAMBLE vs HOW_SOLO contradiction

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Components** | `apps/worker/prompts.py` |
| **Dependencies** | None |
| **Steps** | 1. Split PREAMBLE into `PREAMBLE_DELEGATED` and `PREAMBLE_SOLO`. 2. Delegated: keep "do not cat agent files". 3. Solo: "read agent files before each phase". 4. Wire in `build()`. |
| **Outcome** | Solo runs receive consistent instructions |
| **Regression Risk** | Medium |
| **Validation** | Render solo prompt; verify agent file references present; no "do not cat" in solo |

### R1-004: Add pdf-tools to ingest_pricebook toolset

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Components** | `src/cbc/core/toolsets.py` |
| **Dependencies** | None |
| **Steps** | Add `pdf-tools` to `PROFILES["ingest_pricebook"]` servers list |
| **Outcome** | Ingest job can read PDF sheets |
| **Regression Risk** | Low |
| **Validation** | `toolsets.flags_for("ingest_pricebook")` includes pdf-tools |

---

## Phase 2 — Security

### R2-001: Fail closed on missing internal token in non-dev

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Components** | `apps/api/deps.py`, `src/cbc/config.py` |
| **Dependencies** | None |
| **Steps** | 1. When `APP_ENV` is production/staging, require non-empty `INTERNAL_API_TOKEN`. 2. Raise at startup if missing. |
| **Outcome** | Misconfigured prod cannot start with open API |
| **Regression Risk** | Low |
| **Validation** | Test with `APP_ENV=production` and empty token → startup fails |

### R2-002: Network isolate API in production compose

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Components** | `docker-compose.yml`, deployment docs |
| **Dependencies** | None |
| **Steps** | 1. Remove public API port binding in prod profile. 2. API reachable only from web container on internal network. |
| **Outcome** | Direct API access requires network access to Docker network |
| **Regression Risk** | Medium — breaks direct API debugging in prod |
| **Validation** | `curl localhost:8001` fails from host; web proxy works |

### R2-003: Delimit untrusted content in prompts

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Components** | `apps/worker/prompts.py` |
| **Dependencies** | None |
| **Steps** | Wrap PDF-derived content and filenames in XML delimiters; add instruction to treat delimited content as data not instructions |
| **Outcome** | Reduced prompt injection surface |
| **Regression Risk** | Low |
| **Validation** | Prompt review; adversarial PDF test |

### R2-004: Distributed auth rate limiting

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Components** | `apps/api/routers/auth.py` |
| **Dependencies** | MongoDB |
| **Steps** | Store attempt counts in MongoDB with TTL index; check across replicas |
| **Outcome** | Brute-force protection works with multiple API instances |
| **Regression Risk** | Low |
| **Validation** | Test rate limit from two processes |

---

## Phase 3 — Agent Architecture Repair

### R3-001: Fix pricebook-ingestor stale MCP name

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Components** | `.claude/agents/pricebook-ingestor.md` |
| **Dependencies** | None |
| **Steps** | Replace `pricebook` MCP references with `catalog` |
| **Outcome** | Agent instructions match `.mcp.json` |
| **Regression Risk** | Low |
| **Validation** | Grep `pricebook` MCP in agent file → zero |

### R3-002: Resolve quality-reviewer render instruction mismatch

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Components** | `.claude/agents/quality-reviewer.md`, `apps/worker/prompts.py` |
| **Dependencies** | None |
| **Steps** | 1. Add `Bash` to quality-reviewer tools allowlist. 2. Align agent body to use `scripts/render_review_summary.py`. |
| **Outcome** | Review summary renders consistently |
| **Regression Risk** | Low |
| **Validation** | Agent frontmatter includes Bash; body references script |

### R3-003: Deduplicate HARDWARE GROUPS extraction

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Components** | `.claude/agents/spec-scope-analyst.md`, `.claude/agents/takeoff-engineer.md` |
| **Dependencies** | None |
| **Steps** | spec-scope-analyst records page locations only; takeoff-engineer owns full HW group parsing |
| **Outcome** | Single authoritative HW group data |
| **Regression Risk** | Medium |
| **Validation** | Pipeline run; compare scope_summary vs door_schedule HW data |

### R3-004: Convert quote-builder to deterministic service

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Components** | `apps/worker/main.py`, `src/cbc/services/` |
| **Dependencies** | R3-002 pattern |
| **Steps** | 1. Add `render_quotation(slug)` service calling `validate_and_render_quote.py`. 2. Run after pricing sync in worker for `build_proposal`. 3. Agent becomes optional override only. |
| **Outcome** | Quotation HTML always from validated script |
| **Regression Risk** | Medium |
| **Validation** | build_proposal produces quotation.html without Claude writing HTML |

### R3-005: Extend validate_project.py for review flags

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Components** | `scripts/validate_project.py` → `src/cbc/validation/` |
| **Dependencies** | R4-002 |
| **Steps** | Port quality-reviewer flag table to deterministic checks; agent generates RFI prose only |
| **Outcome** | Review flags reproducible without LLM |
| **Regression Risk** | Medium |
| **Validation** | Same input → same flags |

### R3-006: Apply MCP scoping to headless workflows

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Components** | `workflows/_phase.sh`, `src/cbc/core/toolsets.py` |
| **Dependencies** | None |
| **Steps** | 1. Map phase scripts to job types. 2. Generate `--mcp-config` from toolsets.py. 3. Add `--strict-mcp-config`. 4. Handle solo vs delegated in shell. |
| **Outcome** | Headless and Ops-Hub paths have same tool surface |
| **Regression Risk** | Medium |
| **Validation** | Compare MCP flags between worker and `_phase.sh` for same phase |

---

## Phase 4 — Backend Refactoring

### R4-001: Remove kernel layer violation

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Components** | `src/cbc/core/toolsets.py` |
| **Dependencies** | None |
| **Steps** | 1. Read `MONGODB_READONLY_URI` from env only in toolsets. 2. Remove `cbc.db` import. 3. Worker passes URI if needed. |
| **Outcome** | `cbc/core/` has no upward imports |
| **Regression Risk** | Low |
| **Validation** | `tests/api/test_layering.py` passes; grep `from cbc.db` in core → zero |

### R4-002: Move validation to domain layer

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Components** | `scripts/validate_project.py` → `src/cbc/validation/` |
| **Dependencies** | None |
| **Steps** | 1. Create `src/cbc/validation/artifacts.py`. 2. Move `validate_job_artifacts` and helpers. 3. Update worker import. 4. Keep CLI wrapper in scripts. |
| **Outcome** | Validation is domain code, not script |
| **Regression Risk** | Low |
| **Validation** | `pytest tests`; worker imports from `cbc.validation` |

### R4-003: Split sync.py

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Components** | `src/cbc/services/sync.py` |
| **Dependencies** | R4-002 |
| **Steps** | 1. Create `sync/extraction.py`, `sync/pricing.py`, `sync/proposal.py`, `sync/geometry.py`. 2. Re-export from `sync/__init__.py`. 3. Move `sync_results()` orchestration from worker to service. |
| **Outcome** | Focused modules with clear phase boundaries |
| **Regression Risk** | Medium |
| **Validation** | All sync tests pass; import paths updated |

### R4-004: Consolidate reference data

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Components** | `.claude/memory/`, `reference-library/` |
| **Dependencies** | None |
| **Steps** | 1. Declare `reference-library/*.json` canonical. 2. Replace memory file content with pointers to JSON paths. 3. Add generation script for agent-readable summaries if needed. |
| **Outcome** | Single source of truth for margins, tax, vendors |
| **Regression Risk** | Medium — agents may miss context |
| **Validation** | Edit JSON → API and agent see same values |

### R4-005: Drop documentIndexes collection

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Components** | `src/cbc/db.py`, migration script |
| **Dependencies** | R1-001 |
| **Steps** | Remove collection accessor, indexes, and any migration to drop existing data |
| **Outcome** | Clean Mongo schema |
| **Regression Risk** | Low |
| **Validation** | `db.list_collection_names()` has no documentIndexes |

---

## Phase 5 — Frontend Repair

### R5-001: Surface marginCheck in quote UI

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Components** | `web/components/quote/quote-client.tsx`, `line-item-row` patterns |
| **Dependencies** | None |
| **Steps** | 1. Read `marginCheck` from API response. 2. Show below-band badge per line. 3. Add filter for below-band lines. |
| **Outcome** | NFR-8 visibility in UI |
| **Regression Risk** | Low |
| **Validation** | Line with margin below floor shows badge |

### R5-002: Fix Playwright E2E failures

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Components** | `web/e2e/auth.spec.ts`, `theme.spec.ts`, `catalog.spec.ts` |
| **Dependencies** | Running stack |
| **Steps** | 1. Configure test credentials in env. 2. Fix theme toggle strict mode (scope to navigation). 3. Fix catalog search selectors. |
| **Outcome** | E2E suite reliable in CI |
| **Regression Risk** | Low |
| **Validation** | `npx playwright test` all pass |

### R5-003: Add reuse-prior-quote UI entry point

| Field | Value |
|-------|-------|
| **Priority** | P3 |
| **Components** | `web/components/bids/`, API endpoint |
| **Dependencies** | FR-11 scope decision |
| **Steps** | Add "Find similar quote" action on templated bids; enqueue search job or display matches |
| **Outcome** | FR-11 accessible from Ops-Hub |
| **Regression Risk** | Low |
| **Validation** | Templated bid shows prior quote suggestions |

---

## Phase 6 — Data and Retrieval Improvements

### R6-001: Align auditability rule with validator

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Components** | `.claude/rules/auditability.md`, `scripts/validate_project.py` |
| **Dependencies** | None |
| **Steps** | Add `bbox` and `page_size` to auditability rule as required for sheet viewer traceability |
| **Outcome** | Rule and validator agree on NFR-3 |
| **Regression Risk** | None |
| **Validation** | Rule text matches validator checks |

### R6-002: Fix silent bbox attachment failures

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Components** | `src/cbc/services/sync.py:627` |
| **Dependencies** | None |
| **Steps** | Log warning with opening ID on PDF open failure; add flag to opening record |
| **Outcome** | Bbox failures visible in logs and UI |
| **Regression Risk** | Low |
| **Validation** | Corrupt PDF path logs warning |

### R6-003: Document PageIndex scaling limit

| Field | Value |
|-------|-------|
| **Priority** | P3 |
| **Components** | `src/cbc/pageindex/query.py`, docs |
| **Dependencies** | None |
| **Steps** | Document that Python scoring loads all catalogs; plan Mongo text index usage at 50+ catalogs |
| **Outcome** | Operators know when to optimize |
| **Regression Risk** | None |
| **Validation** | Doc exists in pageindex README |

### R6-004: Coalesce index_catalog jobs

| Field | Value |
|-------|-------|
| **Priority** | P3 |
| **Components** | `src/cbc/services/jobs.py`, `apps/api/routers/price_books.py` |
| **Dependencies** | None |
| **Steps** | Skip enqueue if index fresh (hash match) or coalesce on filename |
| **Outcome** | No redundant parallel indexing |
| **Regression Risk** | Low |
| **Validation** | Re-upload same file → no new job if hash unchanged |

---

## Phase 7 — Testing

### R7-001: Add E2E to CI

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Components** | `.github/workflows/ci.yml` |
| **Dependencies** | R5-002 |
| **Steps** | Add Playwright job with docker compose services |
| **Outcome** | E2E regressions caught in CI |
| **Regression Risk** | Medium — flaky tests block CI |
| **Validation** | PR triggers E2E job |

### R7-002: Add pipeline integration test

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Components** | `tests/pipeline/` |
| **Dependencies** | Mock Claude or recorded fixtures |
| **Steps** | Test worker sync_results for each job type with frozen artifact fixtures |
| **Outcome** | Sync logic tested without Claude |
| **Regression Risk** | Low |
| **Validation** | New tests pass |

### R7-003: Add security probe tests

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Components** | `tests/api/` |
| **Dependencies** | R2-001 |
| **Steps** | Test: no token → 401; path traversal upload → 422; oversized upload → 413 |
| **Outcome** | Security regressions caught |
| **Regression Risk** | Low |
| **Validation** | Tests pass |

---

## Phase 8 — Performance and Scalability

### R8-001: Add structured logging

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Components** | `apps/api/`, `apps/worker/`, `src/cbc/` |
| **Dependencies** | None |
| **Steps** | 1. JSON log format option via env. 2. Include job_id, project_code, actor in worker logs. |
| **Outcome** | Logs parseable by aggregation tools |
| **Regression Risk** | Low |
| **Validation** | `LOG_FORMAT=json` produces JSON lines |

### R8-002: Add job metrics endpoint

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Components** | `apps/api/routers/`, admin settings |
| **Dependencies** | R8-001 |
| **Steps** | Expose job queue depth, avg duration, failure rate from MongoDB aggregations |
| **Outcome** | Basic operational visibility |
| **Regression Risk** | Low |
| **Validation** | Admin dashboard shows metrics |

### R8-003: Evaluate PageIndex text index at scale

| Field | Value |
|-------|-------|
| **Priority** | P3 |
| **Components** | `src/cbc/pageindex/query.py` |
| **Dependencies** | R6-003 |
| **Steps** | Benchmark Python scoring vs Mongo `$text` at 50/100/200 catalogs |
| **Outcome** | Data-driven retrieval optimization decision |
| **Regression Risk** | Low |
| **Validation** | Benchmark report in docs |

---

## Phase 9 — Cleanup and Deletion

### R9-001: Delete dead package directories

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Components** | `src/cbc/catalog/`, `src/cbc/documents/`, `mcp-servers/document-index/`, `mcp-servers/pricebook/`, `frontend/` |
| **Dependencies** | R0-001 |
| **Steps** | Delete directories containing only `__pycache__` |
| **Outcome** | Clean repo tree |
| **Regression Risk** | Low |
| **Validation** | Directories gone; tests pass |

### R9-002: Rewrite stale ops docs

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Components** | `docs/opshub_setup.md`, `.env.example`, `mcp-servers/README.md` |
| **Dependencies** | R1-001, R9-001 |
| **Steps** | Remove document-index, SQLite FTS, index_document references; document PageIndex bootstrap |
| **Outcome** | Docs match code |
| **Regression Risk** | None |
| **Validation** | Grep stale terms → zero in ops docs |

### R9-003: Remove catalog_index_path parameter

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Components** | `src/cbc/core/claude_cli.py`, `src/cbc/core/toolsets.py` |
| **Dependencies** | None |
| **Steps** | Remove ignored parameter and all call sites |
| **Outcome** | Clean CLI spawn API |
| **Regression Risk** | Low |
| **Validation** | Grep `catalog_index_path` → zero |

### R9-004: Remove stale scripts references

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Components** | `scripts/ingest_phase1_pricebooks.py` |
| **Dependencies** | R9-002 |
| **Steps** | Update print statements referencing `cbc.catalog.rebuild` |
| **Outcome** | Scripts output accurate instructions |
| **Regression Risk** | None |
| **Validation** | Run script --help; no stale module references |

---

## Task Dependency Graph

```
R0-001 → R1-001, R9-001
R1-003 → (validates solo path)
R4-002 → R3-005, R4-003
R5-002 → R7-001
R2-001 → R7-003
R1-001 → R4-005, R9-002
```

## Estimated Timeline

| Phase | Duration | Tasks |
|-------|----------|-------|
| 0 | 0.5 day | 2 |
| 1 | 2 days | 4 |
| 2 | 2 days | 4 |
| 3 | 3 days | 6 |
| 4 | 4 days | 5 |
| 5 | 2 days | 3 |
| 6 | 1 day | 4 |
| 7 | 2 days | 3 |
| 8 | 2 days | 3 |
| 9 | 1 day | 4 |
| **Total** | **~20 days** | **34 tasks** |
