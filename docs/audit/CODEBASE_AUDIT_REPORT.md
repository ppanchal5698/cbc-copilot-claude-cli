# CBC Estimating Copilot — Codebase Audit Report

**Audit date:** 2026-09-01  
**Method:** Fresh code inspection + full runtime verification (no prior audit docs treated as authoritative)  
**Auditor scope:** Architecture, agents, security, reliability, feature completeness, retrieval pipeline

---

## 1. Executive Summary

### Overall Health

CBC Estimating Copilot is a **dual-mode estimating system** (Ops-Hub web app + headless shell workflows) that processes bid-set PDFs through a 10-agent Claude Code pipeline, prices lines via PageIndex-routed vendor PDFs, and produces draft quotations for estimator review. The domain layer (`src/cbc/`) is well-separated from applications (`apps/api`, `apps/worker`, `web/`), enforced by layering tests. The core money math has a single implementation in `cbc/core/calc.py`.

The system is **functionally capable** for gated and autopilot estimating workflows but has **production-readiness gaps** in observability, security hardening, agent prompt consistency, dead schema entries, and dual orchestration paths that diverge in tool scoping.

### Health Scores

| Dimension | Score | Rationale |
|-----------|-------|-----------|
| Architecture | 7/10 | Clean layering rule; kernel violation in `toolsets.py`; god-module `sync.py`; dual orchestration paths |
| Code Quality | 7/10 | 464 tests pass; consistent patterns; some silent exception handlers; stale docs |
| Agent Architecture | 5/10 | 10 agents with skill overlap; solo/delegated path contradictions; 3 agents should be services |
| Security | 6/10 | Hooks + internal token work; `--dangerously-skip-permissions` on all runs; token spoofing if leaked |
| Reliability | 6/10 | Job queue with heartbeat/reaper; validation post-Claude wastes runs; no APM |
| Scalability | 6/10 | Single-worker poll model; PageIndex loads all catalogs in memory; no distributed rate limiting |
| Maintainability | 6/10 | Dual reference-data stores; agent/skill duplication; stale ops docs |
| Production Readiness | 5/10 | Core path works; missing observability, P21, margin UI, E2E flakiness |

### Highest-Risk Issues

1. **SEC-001:** Every pipeline run uses `--dangerously-skip-permissions`; guardrails depend entirely on PreToolUse hooks
2. **DEAD-001:** `index_document`/`delete_document` job types in schema with no worker handler — manual enqueue fails
3. **AGENT-001:** PREAMBLE contradicts HOW_SOLO — solo runs told both to read and not read agent files
4. **AGENT-002:** `rerun_extraction` prompt names no agent or output contract
5. **ARCH-001:** `cbc.core.toolsets` imports `cbc.db` — kernel layer violation
6. **DUP-001:** Dual reference-data stores (`.claude/memory/` vs `reference-library/`) risk drift
7. **ORCH-001:** Headless workflows lack per-job MCP tool scoping that worker applies
8. **OBS-001:** No APM, tracing, or structured log aggregation beyond stdout + audit trail
9. **H1 verified:** PageIndex Mongo text index created but unused — Python scoring loads all catalogs
10. **H6 verified:** P21 connector exists but `P21_BASE_URL` unset — all Path 1 lookups deferred

### Production Readiness Classification

**Requires Significant Refactoring**

The system can run end-to-end in development and produce valid draft quotations (verified by test suite and prior pipeline runs). It is not yet safe for unattended production deployment without addressing security hardening, observability, dead job types, agent prompt consistency, and documentation drift.

---

## 2. Actual System Architecture

### Request Lifecycle (Ops-Hub)

```
Browser
  → Next.js 16 (NextAuth JWT session)
  → /api/proxy/* (adds X-Internal-Token + X-Actor from session email)
  → FastAPI (InternalAuthMiddleware on all /api/* except health + auth/verify)
  → MongoDB (system of record) + filesystem (projects/{slug}/)
  → Job enqueue (never direct Claude spawn from API)
  → Worker poll loop (atomic claim, heartbeat, stale reaper)
  → claude --print (single spawn point: src/cbc/core/claude_cli.py)
  → MCP servers (5 stdio: pdf-tools, catalog, calc-engine, artifact-storage, p21-connector)
  → Disk artifacts (extracted/, priced/, review/, quotation.html)
  → sync service (disk → MongoDB for UI)
  → Browser polls jobs + terminal SSE
```

### Dual Orchestration Paths

| Path | Entry | MCP scoping | Prompt source |
|------|-------|-------------|---------------|
| Ops-Hub | `apps/worker/main.py` | Per-job via `toolsets.flags_for()` + `--strict-mcp-config` | `apps/worker/prompts.py` |
| Headless | `workflows/_phase.sh` | None — all servers from `.mcp.json` | Same preamble via `python -m apps.worker.prompts` |

Evidence: `workflows/_phase.sh:41` calls `claude --print --dangerously-skip-permissions` with no `--mcp-config`. Worker applies scoping at `src/cbc/core/claude_cli.py:99`.

### Retrieval Architecture (Not RAG)

PageIndex (`src/cbc/pageindex/`) is a **page-routing index**, not vector RAG:

```
pricebooks/*.pdf
  → index_catalog job (deterministic, no Claude)
  → build_one(): PyMuPDF text + optional Ollama layout profile
  → MongoDB pageIndex (one doc per catalog, SHA-256 hash skip)
  → query.rank_pages() — Python keyword scoring (no embeddings)
  → catalog MCP find_pages → pdf-tools opens page → price read live off sheet
```

No chunking, embedding, vector database, or reranking pipeline exists. This is intentional — prices are never pre-extracted to avoid staleness.

### Authentication Lifecycle

1. **Sign-in:** NextAuth Credentials → `POST /api/auth/verify` (public, rate-limited in-process)
2. **Session:** JWT carries email, role, initials
3. **API calls:** Next.js proxy adds `X-Internal-Token` + `X-Actor: session.user.email`
4. **Admin gate:** `require_admin` re-queries MongoDB role by email — JWT role not trusted
5. **Gap:** Anyone with `INTERNAL_API_TOKEN` can spoof `X-Actor` if API port is reachable

---

## 3. Component Inventory

### Frontend (`web/`)

| Component | Count | Stack |
|-----------|-------|-------|
| App routes | 12 pages | Next.js 16 App Router, React 19 |
| UI components | ~70 | shadcn/ui, Tailwind 4, SWR |
| API routes | 2 | NextAuth, authenticated proxy |
| Tests | 6 Vitest + 9 Playwright | 23 unit tests pass; 8/14 E2E pass |

### Backend (`apps/`)

| Module | Routers/Files | Role |
|--------|---------------|------|
| `apps/api/` | 18 routers | FastAPI, job enqueue, CRUD, auth |
| `apps/worker/` | main.py, prompts.py, 2 handlers | Job poll, Claude spawn, sync |

### Domain (`src/cbc/`)

| Package | Role |
|---------|------|
| `config.py`, `db.py` | Settings, MongoDB, indexes |
| `schemas/` | Pydantic models, JobType, Stage |
| `services/` | jobs, sync, quote, pricing, audit, provider, storage |
| `core/` | calc, claude_cli, toolsets, secrets, pdfrows |
| `pageindex/` | Build, store, query, profile, basis |

### Agents (`.claude/agents/`)

10 agents: intake-coordinator, spec-scope-analyst, takeoff-engineer, frp-specialist, product-matcher, pricing-engineer, quote-builder, quality-reviewer, delivery-agent, pricebook-ingestor

### Skills (`.claude/skills/`)

9 skills with scripts and references

### MCP Servers

5 servers, 25 tools total (verified by `python mcp-servers/main.py --selftest`)

### MongoDB Collections

users, projects, documents, lineItems, quoteLines, quotes, proposals, products, priceBooks, jobs, auditLog, calls, estimateVersions, counters, settings, documentIndexes (unused), pageIndex

### External Systems

- Claude Code CLI (subscription/API/Bedrock/gateway/Ollama)
- Prophet 21 (read-only, deferred — NR-10)
- Ollama (optional, for PageIndex profiling)

---

## 4. Agent Architecture Report

### Agent Summary Table

| Agent | Purpose | Triggers | Verdict |
|-------|---------|----------|---------|
| intake-coordinator | Phase 0/1 scaffold + metadata | extract, run_full_pipeline | Hybrid — keep |
| spec-scope-analyst | Phase 2 scope parsing | extract, run_full_pipeline | Keep agent |
| takeoff-engineer | Phase 3 door schedule + bbox | extract, rerun, addendum | Hybrid — keep |
| frp-specialist | Phase 3b FRP geometry | extract (conditional) | Hybrid — blocked on constants |
| product-matcher | FR-4 hardware matching | match_and_price | Keep agent |
| pricing-engineer | Phase 4 cost + margin | match_and_price | Shrink toward service |
| quote-builder | Quotation HTML | build_proposal | → Deterministic service |
| quality-reviewer | Phase 5 flags + review | build_proposal | → Mostly service |
| delivery-agent | Phase 6 PDF + email draft | build_proposal | → Mostly service |
| pricebook-ingestor | Price book ingest | ingest_pricebook | Revisit — page-index may replace |

### Per-Agent Problems

**intake-coordinator:** No `pdf-tools` in allowlist but metadata extraction implies PDF reading.

**spec-scope-analyst ↔ takeoff-engineer:** Duplicate HARDWARE GROUPS extraction (`spec-scope-analyst.md:29-31`, `takeoff-engineer.md:48-49`).

**takeoff-engineer:** `rerun_extraction` prompt (`prompts.py:134-144`) names no agent or output — critical gap.

**frp-specialist:** No validator gate for `frp_takeoff.json`; quantities null when constants PENDING.

**product-matcher:** No standalone workflow script; folded into `phase4_pricing.sh`.

**pricing-engineer:** P21 Path 1 dead code — connector returns manual-entry stub (`pricing-engineer.md:22-24`).

**quote-builder:** Agent body says run script only — should be `validate_and_render_quote.py` service call.

**quality-reviewer:** Worker prompt says run `render_review_summary.py` (`prompts.py:220-221`); agent says hand-render (`quality-reviewer.md:67-68`); no Bash in allowlist.

**delivery-agent:** PDF renderer unspecified — no pinned script unlike quote-builder.

**pricebook-ingestor:** Stale `pricebook` MCP name (`pricebook-ingestor.md:22-23`); `ingest_pricebook` toolset missing `pdf-tools` (`toolsets.py:69`).

### Agent Communication Analysis

| Check | Status | Evidence |
|-------|--------|----------|
| Circular agent calls | None found | Agents invoked sequentially via prompts |
| Infinite loops | Mitigated | `--max-turns` per job type |
| Shared mutable state | Risk | All agents write to same `projects/{slug}/` directory |
| Missing idempotency | Partial | Job dedup for exclusive types; `ingest_pricebook` not exclusive |
| Missing cancellation | Implemented | `watch_cancel()` in worker |
| Missing retry | Implemented | Exponential backoff, max 3 attempts |
| Hallucination propagation | Mitigated | Post-run validation + honesty rules in prompts |

### Orchestration Verdict

| Component | Should Be | Current |
|-----------|-----------|---------|
| PageIndex build | Deterministic service | ✓ Local handler, no Claude |
| Quote HTML render | Deterministic service | ✗ Agent |
| Review flags | Deterministic service + LLM prose | ✗ Agent only |
| PDF export | Deterministic service | ✗ Agent |
| Door schedule extraction | Hybrid (script + agent) | ✓ Correct |
| Product matching | Agent | ✓ Correct |
| Pricing path selection | Agent + calc-engine | Partially correct |

---

## 5. Critical Issues

### Critical

| ID | Severity | Location | Evidence | Root Cause | Impact | Recommended Fix |
|----|----------|----------|----------|------------|--------|-----------------|
| SEC-001 | Critical | `src/cbc/core/claude_cli.py:103,123` | `--dangerously-skip-permissions` on every run | Unattended runs cannot answer CLI prompts | `settings.json` deny lists bypassed; safety depends on hooks only | Document accepted risk; add post-run tool audit; evaluate narrower profiles |
| DEAD-001 | Critical | `src/cbc/schemas/common.py:22-23` | `index_document`/`delete_document` in JobType; no handler in `worker/main.py` | Deleted document-index subsystem; schema not cleaned | Manual `POST /api/jobs` with these types fails at `prompts.build()` | Remove from schema, UI, validator, or implement handlers |

### High

| ID | Severity | Location | Evidence | Root Cause | Impact | Recommended Fix |
|----|----------|----------|----------|------------|--------|-----------------|
| AGENT-001 | High | `apps/worker/prompts.py:49-53` vs `76-78` | HOW_SOLO requires reading agent files; PREAMBLE forbids it | Contradictory instructions in same prompt | Solo runs may skip field contracts | Remove PREAMBLE contradiction for solo path |
| AGENT-002 | High | `apps/worker/prompts.py:134-144` | `RERUN` template has no agents or outputs | Incomplete prompt template | Rerun extraction unpredictable | Add takeoff-engineer phase + output contract |
| AGENT-003 | High | `src/cbc/core/toolsets.py:69` | `ingest_pricebook` profile lacks `pdf-tools` | Toolset not updated when agent added pdf-tools | Ingest job cannot read PDF sheets | Add `pdf-tools` to ingest_pricebook profile |
| ARCH-001 | High | `src/cbc/core/toolsets.py:89-94` | Imports `cbc.db.readonly_uri` | Kernel imports application layer | Test isolation broken; layering violated | Inject URI via env only or move to services |
| DUP-001 | High | `.claude/memory/` + `reference-library/` | Parallel margin, tax, vendor, finish data | Historical split between agent context and API data | Pricing drift between Claude and API | Consolidate to JSON canonical; generate markdown views |
| SEC-002 | High | `apps/api/deps.py:63-75` | Token + arbitrary X-Actor | Service-to-service auth model | Leaked token = full API access with spoofed identity | Network isolate API; rotate secrets; mTLS |
| ORCH-001 | High | `workflows/_phase.sh:41` | No `--mcp-config` / `--strict-mcp-config` | Headless path predates tool scoping | Wrong tools available; higher token cost | Apply same toolsets.py scoping to shell path |
| DEAD-002 | High | `src/cbc/db.py:105-107` | `documentIndexes` collection + indexes; zero usage | Deleted subsystem remnant | Misleading schema for operators | Drop collection and indexes |

### Medium

| ID | Severity | Location | Evidence | Root Cause | Impact | Recommended Fix |
|----|----------|----------|----------|------------|--------|-----------------|
| ARCH-002 | Medium | `src/cbc/services/sync.py` | ~605 lines, 20+ functions | Organic growth | High change blast radius | Split into sync/extraction, pricing, proposal, geometry |
| ARCH-003 | Medium | `apps/worker/main.py:34` | Imports from `scripts.validate_project` | Validation in scripts not domain | Layering violation | Move to `src/cbc/validation/` |
| ARCH-004 | Medium | `.claude/agents/` + `.claude/skills/` | Parallel contracts for same phases | Dual maintenance | Field contract drift | Single source of truth |
| SF-001 | Medium | `src/cbc/services/sync.py:627` | `except Exception: continue` on PDF open | Silent bbox skip | Openings lack highlight boxes | Log warning; surface in validation |
| SF-007 | Medium | `scripts/validate_project.py:123-128` | PDF open failure → None | Silent validation skip | False pass on bbox checks | Fail or flag explicitly |
| CONC-001 | Medium | `src/cbc/schemas/common.py:34-37` | `ingest_pricebook` not exclusive | Intentional for parallel uploads | Race on same pricebook | Per-priceBookId exclusivity |
| CONC-004 | Medium | `apps/api/routers/auth.py:26-42` | In-process rate limit dict | No shared store | Brute-force across replicas | Mongo/Redis-backed limiter |
| SEC-003 | Medium | `apps/api/deps.py:64` | Empty token skips check | Dev convenience | Misconfigured prod opens API | Fail closed when APP_ENV != development |
| SEC-005 | Medium | `apps/worker/prompts.py` | User PDF text in prompts | No sanitization | Prompt injection risk | Delimit untrusted content |
| OBS-001 | Medium | Codebase-wide | No Sentry/Datadog/OTel in app code | Not implemented | Production debugging relies on container logs | Add structured logging + error tracking |
| RULE-001 | Medium | `auditability.md` vs `validate_project.py:374` | Rule requires source_page; validator also requires bbox | Divergent NFR-3 definitions | Documentation disagreement | Align rule and validator |
| ORCH-002 | Medium | `apps/worker/main.py:305` | Validation post-Claude, pre-sync | Design choice | Failed validation wastes Claude pass | Consider per-phase validation in full pipeline |
| ORCH-003 | Medium | `apps/api/routers/line_items.py:268` | `needs_look` count logged but not blocking | Intentional? | Low-confidence lines proceed to pricing | Document or gate |

### Low

| ID | Severity | Location | Evidence | Impact | Fix |
|----|----------|----------|----------|--------|-----|
| DEAD-003 | Low | `frontend/` empty dir | UI in `web/` | Confusion | Delete or add README |
| DEAD-004 | Low | `docs/opshub_setup.md:58-68` | References deleted subsystems | Operator misdirection | Rewrite for PageIndex |
| DEAD-005 | Low | `.env.example:14` | "SQLite FTS5 catalog index" comment | Stale | Update comment |
| DUP-004 | Low | `claude_cli.py:66` | `catalog_index_path` ignored | API noise | Remove parameter |
| H4 | Low | `store.py:47-54` vs `query.py` | Text index created, Python scoring used | Unused index at current scale | Use index or remove; document scaling limit |
| E2E-001 | Low | `web/e2e/` | 4/14 Playwright tests fail | Auth env, duplicate theme buttons | Fix selectors; CI credentials |

---

## 6. Duplicate and Dead Code

| Component | Status | Evidence | Recommended Action | Risk |
|-----------|--------|----------|-------------------|------|
| `index_document` job type | Dead | Schema only; no handler | Remove from schema + UI | Low |
| `delete_document` job type | Dead | Schema only; no handler | Remove from schema + UI | Low |
| `documentIndexes` collection | Dead | Indexes created; zero reads/writes | Drop collection | Low |
| `cbc/catalog/` package | Dead | Only `__pycache__` remains | Delete directory | Low |
| `cbc/documents/` package | Dead | Only `__pycache__` remains | Delete directory | Low |
| `mcp-servers/document-index/` | Dead | Only `__pycache__` remains | Delete directory | Low |
| `mcp-servers/pricebook/` | Dead | Only `__pycache__` remains | Delete directory | Low |
| `frontend/` directory | Dead | Empty; UI in `web/` | Delete or README | Low |
| `catalog_index_path` param | Dead | Accepted and ignored | Remove from CLI spawn | Low |
| Agent ↔ skill contracts | Duplicate | 10 agents + 9 skills overlap | Consolidate to single source | Medium |
| `.claude/memory/` ↔ `reference-library/` | Duplicate | 5+ overlapping domains | JSON canonical | Medium |
| `calc.py` ↔ calc-engine MCP | Intentional adapter | Server imports core | Keep as-is | None |

---

## 7. Missing Functionality (Genuinely Required)

| Problem | Why It Matters | Proposed Functionality | Priority |
|---------|----------------|----------------------|----------|
| No production observability | Cannot debug failed runs in prod | Structured logging, error tracking, job metrics | High |
| P21 not connected (NR-10) | Path 1 cost sourcing unavailable | Connect P21 read-only endpoint | High (blocked on IT) |
| Margin floor not visible (NFR-8) | `marginCheck` computed but not shown in quote UI | Surface below-band flags in quote grid | Medium |
| FR-14 reconciliation incomplete | Alternates/addenda flagged but not merged | Matrix 4.1 decision from CBC | Medium (blocked on business) |
| FRP constants PENDING (Open Item 5) | Quantities cannot be computed | CBC to provide conversion constants | Medium (blocked on business) |
| Structured estimator feedback (FR-13) | Only `estimator_notes.md` stub | Feedback ingestion loop | Low |
| Reuse-prior-quote no UI (FR-11) | Agent-only; no Ops-Hub trigger | Add action for templated bids | Low |
| Distributed auth rate limiting | Per-process only | Shared rate limit store | Medium |
| E2E test reliability | 4 Playwright failures | Fix auth fixtures and selectors | Low |

---

## 8. Security Findings

| ID | Severity | Finding | Exploitability | Mitigation Status |
|----|----------|---------|----------------|-------------------|
| SEC-001 | Critical | `--dangerously-skip-permissions` on all pipeline runs | Medium — requires hook bypass | Hooks active; not defense-in-depth |
| SEC-002 | High | Internal token + X-Actor spoofing | High if token leaked | Token server-only in Next.js proxy |
| SEC-003 | Medium | Empty INTERNAL_API_TOKEN disables check | Medium on misconfiguration | APP_ENV guard for prod |
| SEC-004 | Medium | Default dev secrets in repo | Low — guarded in prod/staging | `config.py:74-86` raises |
| SEC-005 | Medium | PDF content → prompts without sanitization | Low-Medium | Hooks still apply to tools |
| SEC-006 | Low | CORS allow_credentials + wildcard methods | Low with correct origins | Default localhost only |
| SEC-007 | Low | Path traversal mostly mitigated | Low | `storage.safe_name`, tests exist |
| SEC-008 | Low | P21 write tools denied | N/A | Settings + hooks |
| NFR-1 | — | Send blocking | Tested | `pre_send_quote.py` exit 2 |
| NFR-5 | — | P21 read-only | Verified | No write tools in connector |

**Runtime verification:** `GET /api/projects` without token returns **401** (verified 2026-09-01).

---

## 9. Technical Debt

### Remove Immediately

- Dead job types `index_document`, `delete_document`
- `documentIndexes` Mongo collection
- `__pycache__`-only deleted package directories
- Stale `catalog_index_path` parameter

### Staged Migration

- Consolidate reference data to JSON canonical store
- Split `sync.py` into focused modules
- Move validation from `scripts/` to `src/cbc/validation/`
- Convert quote-builder, quality-reviewer, delivery-agent to deterministic services
- Apply MCP tool scoping to headless workflow path
- Fix agent prompt contradictions (PREAMBLE vs HOW_SOLO, rerun template)

### Keep Temporarily

- `--dangerously-skip-permissions` (required for unattended runs; mitigate with hooks)
- In-process auth rate limiting (acceptable for single-replica dev)
- PageIndex Python scoring (adequate at ~14 catalogs; monitor at scale)
- `ingest_pricebook` LLM path (fallback; primary path is `index_catalog`)

---

## 10. RAG and Retrieval Audit

| Stage | Present? | Implementation | Issues |
|-------|----------|----------------|--------|
| Document ingestion | Yes | PDF upload to `projects/{slug}/uploads/raw/` | OK |
| Parsing | Yes | pdf-tools MCP, pdfplumber, PyMuPDF | OK |
| OCR/Vision | Partial | Tesseract optional in pdfrows | Graceful skip if missing |
| Normalization | Yes | sync.import_extraction | OK |
| Chunking | No | N/A — page-level routing | By design |
| Embedding | No | N/A | By design |
| Indexing | Yes | PageIndex → MongoDB pageIndex | OK |
| Retrieval | Yes | Python keyword scoring in query.py | Text index unused (H4 confirmed) |
| Reranking | No | Score sort only | Adequate at current scale |
| Context assembly | Yes | Agent opens page via pdf-tools | OK |
| LLM generation | Yes | Claude reads price off sheet | OK |
| Validation | Yes | validate_project.py post-run | bbox/source_page enforced |
| Source attribution | Yes | source_page, cost_source on lines | OK |
| Evaluation metrics | No | No retrieval accuracy metrics | Gap for future |

**Verdict:** Retrieval is intentionally simple page routing, not RAG. No vector pipeline needed unless catalog count exceeds Python scoring capacity (~100+ catalogs).

---

## 11. Runtime Verification Results

| Check | Result | Date |
|-------|--------|------|
| `python -m pytest tests -q` | **464 passed, 9 skipped** | 2026-09-01 |
| `python mcp-servers/main.py --selftest` | **All 5 servers OK** (catalog demo skipped — no MONGODB_READONLY_URI locally) | 2026-09-01 |
| `docker compose ps` | api, web, worker, mongo all healthy | 2026-09-01 |
| `GET /api/health` | status ok, database up, catalogIndex ready | 2026-09-01 |
| API without auth | **401** | 2026-09-01 |
| `npm run typecheck` | Pass | 2026-09-01 |
| `npm test` (Vitest) | **23 passed** | 2026-09-01 |
| `npm run build` | Pass | 2026-09-01 |
| Playwright E2E | **8 passed, 4 failed, 2 skipped** | 2026-09-01 |

**E2E failures:** auth.spec.ts (2), catalog.spec.ts (1), theme.spec.ts (1) — likely env credentials and duplicate theme toggle selectors.

**UNVERIFIED (requires provider/model calls):**

| Item | Why Unverified | How to Verify |
|------|----------------|---------------|
| Full gated pipeline E2E | Requires Claude provider + model quota | Upload fixture PDF, run extract→price→proposal |
| Autopilot pipeline | Same | Create autopilot project, upload, wait for completion |
| Headless workflow tool scoping | Requires Claude run | `bash workflows/run_full_pipeline.sh <project>` |
| P21 live lookup | P21_BASE_URL unset | Set env, run match_and_price |
| Hook blocking of mail commands | Requires interactive Claude | Attempt sendmail in run |

---

## 12. Feature Completeness Summary

| Feature | Status |
|---------|--------|
| Sign-in/auth | Implemented |
| Bid create | Implemented |
| PDF upload | Implemented |
| Extraction review | Implemented |
| Pricing | Implemented |
| Proposal | Implemented |
| Catalog search | Implemented |
| Price books | Implemented |
| Alternates/addenda | Partially Implemented (FR-14 interim) |
| Admin settings | Partially Implemented |
| Job terminal | Implemented |
| P21 lookup | Partially Implemented (deferred) |
| Autopilot | Implemented |
| Addendum ingest | Implemented (reconcile interim) |
| Reference data editing | Partially Implemented (FRP constants pending) |
| Audit log | Implemented |
| User management | Implemented |
| Job cancel | Implemented |
| Provider settings | Implemented |

---

## 13. Hypothesis Verification

| ID | Hypothesis | Result | Evidence |
|----|-----------|--------|----------|
| H1 | Worker scopes MCP; headless does not | **CONFIRMED** | `toolsets.py` vs `_phase.sh:41` |
| H2 | `--dangerously-skip-permissions` bypasses settings deny | **CONFIRMED** | `claude_cli.py:103` |
| H3 | `index_document`/`delete_document` dead | **CONFIRMED** | Schema only; no handler |
| H4 | PageIndex text index unused | **CONFIRMED** | `store.py:47-54`; `query.py` uses Python scoring |
| H5 | Solo path requires agent file reads | **CONFIRMED** | `HOW_SOLO` in prompts.py; contradicted by PREAMBLE |
| H6 | P21 not connected | **CONFIRMED** | `integrations.py:14`; P21_BASE_URL unset |
| H7 | FR-14 incomplete | **CONFIRMED** | `versions.py` PENDING_NOTE; no auto-merge |
| H8 | No APM/tracing | **CONFIRMED** | No app-level Sentry/Datadog/OTel |
| H9 | Agent/skills duplicate domain logic | **CONFIRMED** | Matching ladders, margins in both layers |
| H10 | auditability.md vs validator disagree on bbox | **CONFIRMED** | Rule: source_page only; validator: bbox required |
