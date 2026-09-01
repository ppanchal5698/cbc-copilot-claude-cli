# CBC Estimating Copilot — Implementation Roadmap

**Audit date:** 2026-09-01  
**Ordering:** Production-breaking → Security → Data integrity → Agent correctness → Functional bugs → Architectural cleanup → Performance → New functionality

---

## Legend

| Tag | Meaning |
|-----|---------|
| **QW** | Quick Win — < 1 day, low risk |
| **HR** | High-Risk — requires careful testing, may break runs |
| **BR** | Breaking Change — API or behavior change |
| **SR** | Safe Refactor — no behavior change |
| **MG** | Requires Migration — data or config migration |
| **DEL** | Can Be Deleted |

---

## Tier 1: Production-Breaking Issues

| ID | Task | Tag | Effort | Components |
|----|------|-----|--------|------------|
| R1-001 | Remove dead job types `index_document`/`delete_document` | QW, DEL | 2h | schemas, web, validator |
| R1-002 | Fix `rerun_extraction` prompt (no agent/output) | HR | 4h | prompts.py |
| R1-003 | Fix PREAMBLE vs HOW_SOLO contradiction | HR | 4h | prompts.py |
| R1-004 | Add pdf-tools to ingest_pricebook toolset | QW | 1h | toolsets.py |
| R9-001 | Delete dead `__pycache__` package dirs | QW, DEL | 1h | 5 directories |

**Exit criteria:** No enqueueable job types without handlers; solo prompts consistent; ingest can read PDFs.

---

## Tier 2: Security Vulnerabilities

| ID | Task | Tag | Effort | Components |
|----|------|-----|--------|------------|
| R0-002 | Document accepted security posture | QW | 2h | docs |
| R2-001 | Fail closed on missing token in prod | QW, BR | 2h | deps.py, config.py |
| R2-002 | Network isolate API in prod compose | HR, MG | 4h | docker-compose |
| R2-003 | Delimit untrusted content in prompts | SR | 4h | prompts.py |
| R2-004 | Distributed auth rate limiting | MG | 1d | auth.py |
| R7-003 | Add security probe tests | QW | 4h | tests/api |

**Exit criteria:** Prod cannot start without token; API not publicly reachable; security tests in CI.

---

## Tier 3: Data Integrity

| ID | Task | Tag | Effort | Components |
|----|------|-----|--------|------------|
| R4-004 | Consolidate reference data to JSON canonical | HR, MG | 2d | memory/, reference-library/ |
| R6-001 | Align auditability rule with validator (bbox) | QW | 1h | auditability.md |
| R6-002 | Fix silent bbox attachment failures | SR | 2h | sync.py |
| R4-005 | Drop documentIndexes collection | QW, DEL, MG | 2h | db.py |
| R6-004 | Coalesce index_catalog jobs | SR | 4h | jobs.py |

**Exit criteria:** Single reference data source; bbox failures logged; clean Mongo schema.

---

## Tier 4: Agent Correctness

| ID | Task | Tag | Effort | Components |
|----|------|-----|--------|------------|
| R3-001 | Fix pricebook-ingestor stale MCP name | QW | 1h | agent md |
| R3-002 | Fix quality-reviewer render mismatch | QW | 2h | agent md, prompts |
| R3-003 | Deduplicate HW GROUPS extraction | HR | 4h | 2 agent files |
| R3-006 | Apply MCP scoping to headless workflows | HR | 1d | _phase.sh, toolsets |
| R3-004 | Convert quote-builder to service | HR | 1d | worker, services |
| R3-005 | Deterministic review flags | HR | 2d | validation/ |

**Exit criteria:** Headless and worker paths equivalent; render phases deterministic; agent instructions accurate.

---

## Tier 5: Functional Bugs

| ID | Task | Tag | Effort | Components |
|----|------|-----|--------|------------|
| R5-001 | Surface marginCheck in quote UI | QW | 4h | quote-client.tsx |
| R5-002 | Fix Playwright E2E failures | SR | 1d | e2e/ |
| R9-002 | Rewrite stale ops docs | QW | 4h | docs/ |
| R9-004 | Remove stale script references | QW | 1h | scripts/ |

**Exit criteria:** Below-band margins visible; E2E passes; docs accurate.

---

## Tier 6: Architectural Cleanup

| ID | Task | Tag | Effort | Components |
|----|------|-----|--------|------------|
| R4-001 | Remove kernel layer violation | SR | 2h | toolsets.py |
| R4-002 | Move validation to domain layer | SR | 4h | validation/ |
| R4-003 | Split sync.py | SR | 2d | services/sync/ |
| R9-003 | Remove catalog_index_path param | QW, DEL | 1h | claude_cli.py |
| R7-002 | Add pipeline integration tests | SR | 1d | tests/pipeline |

**Exit criteria:** Layering tests pass; sync modularized; validation in domain.

---

## Tier 7: Performance

| ID | Task | Tag | Effort | Components |
|----|------|-----|--------|------------|
| R8-001 | Structured JSON logging | QW | 4h | api, worker |
| R8-002 | Job metrics endpoint | SR | 1d | api, admin UI |
| R6-003 | Document PageIndex scaling limit | QW | 2h | docs |
| R8-003 | Benchmark text index vs Python scoring | SR | 1d | pageindex/ |

**Exit criteria:** JSON logs available; admin sees queue metrics; scaling documented.

---

## Tier 8: New Functionality (Blocked or Low Priority)

| ID | Task | Tag | Effort | Blocked On |
|----|------|-----|--------|------------|
| — | Connect P21 (NR-10) | HR | 2d | IT endpoint confirmation |
| — | FR-14 alternates reconciliation | HR | 3d | CBC Matrix 4.1 decision |
| — | FRP conversion constants | QW | 2h | CBC Open Item 5 |
| R5-003 | Reuse-prior-quote UI (FR-11) | SR | 1d | Product decision |
| — | Structured estimator feedback (FR-13) | SR | 2d | Product decision |
| R7-001 | E2E in CI | SR | 1d | R5-002 complete |

---

## Sprint Plan (Recommended)

### Sprint 1 (Week 1): Stop the Bleeding

| Day | Tasks |
|-----|-------|
| 1 | R0-001, R0-002, R1-001, R1-004, R9-001 |
| 2 | R1-002, R1-003 |
| 3 | R2-001, R3-001, R3-002, R6-001 |
| 4 | R5-001, R9-002, R9-004 |
| 5 | R7-003, validation run, sprint review |

**Deliverables:** No dead job types; solo prompts fixed; security tests; margin UI; docs updated.

### Sprint 2 (Week 2): Harden

| Day | Tasks |
|-----|-------|
| 1-2 | R3-006 (headless MCP scoping) |
| 3 | R4-001, R4-002 |
| 4 | R6-002, R4-005 |
| 5 | R8-001, R5-002 |

**Deliverables:** Unified orchestration; clean layering; logging; E2E fixed.

### Sprint 3 (Week 3): Simplify Agents

| Day | Tasks |
|-----|-------|
| 1-2 | R3-004 (quote-builder → service) |
| 3-4 | R3-005 (deterministic review) |
| 5 | R3-003, R4-004 start |

**Deliverables:** Render phases deterministic; reference data consolidation started.

### Sprint 4 (Week 4): Consolidate

| Day | Tasks |
|-----|-------|
| 1-2 | R4-004 complete |
| 3-4 | R4-003 (split sync) |
| 5 | R8-002, R7-002, sprint review |

**Deliverables:** Modular sync; single reference store; metrics; integration tests.

---

## Risk Matrix

| Task | Probability of Regression | Impact if Regresses | Mitigation |
|------|--------------------------|---------------------|------------|
| R1-003 PREAMBLE fix | Medium | Solo runs fail validation | Test with Ollama provider |
| R3-004 quote-builder service | Medium | Missing quotation.html | Keep agent as fallback initially |
| R3-006 headless scoping | Medium | Headless runs lose tools | Map each phase to job type carefully |
| R4-004 reference consolidation | Medium | Agent missing context | Keep memory files as pointers, not deletes |
| R4-003 sync split | Low | Import errors | Re-export from __init__ |
| R2-002 network isolate | Low | Dev workflow change | Use dev compose profile with exposed ports |

---

## Can Be Deleted (No Migration Needed)

| Item | Task ID |
|------|---------|
| `index_document`/`delete_document` job types | R1-001 |
| `src/cbc/catalog/` directory | R9-001 |
| `src/cbc/documents/` directory | R9-001 |
| `mcp-servers/document-index/` directory | R9-001 |
| `mcp-servers/pricebook/` directory | R9-001 |
| `frontend/` empty directory | R9-001 |
| `catalog_index_path` parameter | R9-003 |
| `documentIndexes` Mongo collection | R4-005 |

---

## Requires Migration

| Item | Task ID | Migration Steps |
|------|---------|-------------------|
| Reference data consolidation | R4-004 | Audit memory vs JSON diffs; merge; update agent @ refs |
| documentIndexes drop | R4-005 | `db.documentIndexes.drop()` in fresh_reset |
| Prod API network isolation | R2-002 | Update compose prod profile; verify web proxy |
| Distributed rate limiting | R2-004 | Create MongoDB TTL collection for attempts |

---

## Quick Wins Summary (< 1 day total)

1. R1-001 — Remove dead job types
2. R1-004 — Add pdf-tools to ingest toolset
3. R3-001 — Fix stale MCP name in agent
4. R6-001 — Align auditability rule
5. R9-001 — Delete dead directories
6. R9-003 — Remove catalog_index_path
7. R2-001 — Fail closed on missing token
8. R5-001 — Surface marginCheck in UI
9. R8-001 — JSON logging
10. R0-002 — Document security posture

**Estimated quick wins effort:** ~2 days for all 10.

---

## Success Metrics

| Metric | Current | Target (30 days) |
|--------|---------|------------------|
| pytest pass rate | 464/464 | 470+ (new security/sync tests) |
| Playwright pass rate | 8/14 | 14/14 |
| Dead job types | 2 | 0 |
| Agent count (reasoning) | 10 | 6 |
| Deterministic render phases | 0 | 3 |
| Reference data stores | 2 | 1 |
| Kernel layer violations | 1 | 0 |
| Stale doc references | 5+ | 0 |
| Production observability | Logs only | JSON logs + metrics |
