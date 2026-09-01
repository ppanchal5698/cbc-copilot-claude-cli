# CBC Estimating Copilot — Architectural Decision Log

**Audit date:** 2026-09-01  
**Purpose:** Record major recommendations to prevent reintroducing architectural mistakes.

---

## ADR-001: Retain Modular Monolith (No Microservices)

### Decision
Keep the current three-container deployment (web, api+worker, mongo) as a modular monolith. Do not split into microservices.

### Current Problem
Dual orchestration paths (Ops-Hub worker vs headless workflows) create confusion about which path is authoritative.

### Alternatives Considered
1. **Microservices** — separate extraction, pricing, and delivery services
2. **Event-driven architecture** — Kafka/SQS between phases
3. **Status quo** — modular monolith with shared `src/cbc` domain

### Chosen Approach
Modular monolith with strict layering (`apps/*` → `cbc` → nothing above).

### Why
- Single team, single deployment cadence
- MongoDB job queue is adequate for current volume
- Shared filesystem for `projects/` required anyway
- Microservices would add network complexity without proven scaling need

### Tradeoffs
- Worker is single-point for job processing (mitigated by horizontal worker replicas with atomic claim)
- Cannot scale extraction and pricing independently (not needed at current volume)

### Migration Impact
None. Consolidate orchestration paths (worker and workflows use same toolsets and prompts).

---

## ADR-002: PageIndex Over Vector RAG

### Decision
Retain PageIndex (keyword page routing to vendor PDFs) as the catalog retrieval mechanism. Do not add embeddings or vector database.

### Current Problem
Prior SQLite FTS5 approach pre-extracted product rows with 37.8% bad codes. MongoDB text index exists but is unused.

### Alternatives Considered
1. **Vector RAG** — embed page chunks, semantic search
2. **Hybrid search** — keyword + embeddings with reranking
3. **PageIndex (current)** — keyword scoring, live PDF price reading
4. **Pre-extracted price tables** — store prices in MongoDB products

### Chosen Approach
PageIndex with Python keyword scoring; evaluate MongoDB `$text` at 50+ catalogs.

### Why
- Vendor catalogs are too irregular for reliable pre-extraction
- Prices must be read live off sheets to avoid staleness (NFR-3)
- ~14 catalogs fit in memory; scoring is explainable (required for audit)
- No embedding infrastructure to maintain

### Tradeoffs
- Does not scale to hundreds of catalogs without optimization
- No semantic matching ("storeroom lock" won't find "3400 series")
- LLM must read price off PDF page (slower but accurate)

### Migration Impact
None for current architecture. Monitor catalog count; switch `query.py` to Mongo text index when needed.

---

## ADR-003: Reduce Agents from 10 to 6 (+ 4 Services)

### Decision
Convert quote-builder, quality-reviewer, delivery-agent, and pricebook-ingestor from LLM agents to deterministic services. Retain 6 reasoning agents.

### Current Problem
- Agents doing work that scripts already do (render quote, validate, export PDF)
- Solo provider path cannot delegate; all 10 agent contracts must be read sequentially
- Agent/skill duplication causes field contract drift (32 validation failures documented)

### Alternatives Considered
1. **Keep all 10 agents** — fix prompts only
2. **Single mega-agent** — one LLM call for entire pipeline
3. **6 agents + 4 services** — agents for reasoning, services for deterministic work
4. **Zero agents** — full deterministic pipeline (impossible for PDF interpretation)

### Chosen Approach
6 agents (intake, spec-scope, takeoff, frp, product-matcher, pricing-engineer) + 4 services (render, review, delivery, index).

### Why
- Quote HTML generation is already scripted (`validate_and_render_quote.py`)
- Review flags map to deterministic rules in `validate_project.py`
- PDF export is template fill + WeasyPrint
- PageIndex build is already deterministic (`index_catalog` handler)
- Reduces token cost, increases reliability, simplifies solo path

### Tradeoffs
- Less "agentic" appearance (irrelevant to business outcome)
- RFI prose generation moves to optional LLM call or template
- Requires worker changes to call services between Claude phases

### Migration Impact
- Add `cbc/services/render.py`, `cbc/validation/review.py`, `cbc/services/delivery.py`
- Modify `build_proposal` and `run_full_pipeline` worker paths
- Keep agent `.md` files as documentation references during transition

---

## ADR-004: Accept `--dangerously-skip-permissions` with Hook Defense

### Decision
Continue using `--dangerously-skip-permissions` for unattended pipeline runs. Do not attempt to remove it. Strengthen hook enforcement and post-run auditing.

### Current Problem
Flag bypasses `settings.json` allow/deny lists. All guardrail enforcement depends on PreToolUse hooks.

### Alternatives Considered
1. **Remove flag** — requires interactive permission prompts (breaks unattended runs)
2. **Custom permission profiles** — if Claude CLI supports granular unattended profiles
3. **Accept risk + hooks** — current approach with enhanced auditing
4. **Sandboxed subprocess** — container-level restrictions

### Chosen Approach
Option 3: accept flag; document risk; add post-run tool call audit; keep hooks as primary enforcement.

### Why
- Claude Code refuses unattended runs without this flag
- Hooks (`pre_send_quote`, `pre_delete_guard`) are tested and working
- Container runs as non-root; filesystem mounts are scoped
- Alternative permission profiles not available in current CLI

### Tradeoffs
- Single hook miss = full tool access including Bash
- Defense-in-depth reduced compared to interactive mode
- Must maintain hook coverage as new tools added

### Migration Impact
- Document in ops runbook and `docs/guardrails.md`
- Add post-run audit script comparing tool calls against allowlist
- No code change to `claude_cli.py` required

---

## ADR-005: Consolidate Reference Data to JSON

### Decision
Make `reference-library/*.json` the single canonical store. Convert `.claude/memory/*.md` files to pointers or generated summaries.

### Current Problem
Dual stores for margins, tax, vendors, finishes, frame depths. API writes JSON; agents read markdown. Drift risk.

### Alternatives Considered
1. **JSON canonical** — memory files become pointers
2. **Markdown canonical** — API reads markdown (bad for structured data)
3. **Generated sync** — script generates memory from JSON on change
4. **Status quo** — maintain both manually

### Chosen Approach
JSON canonical with generated markdown summaries for agent context.

### Why
- API and calc engine already consume JSON
- Structured data (margins, tax rates) belongs in structured format
- Generation script ensures agents always see current values
- Admin UI already edits JSON via reference_data API

### Tradeoffs
- Requires generation step in bootstrap or on reference data change
- Agents lose prose context in memory files (mitigated by generated summaries)
- One-time merge effort to reconcile any current diffs

### Migration Impact
- Audit all 13 memory files against JSON counterparts
- Create `scripts/generate_agent_memory.py`
- Update agent `@` references to point to generated files or JSON paths
- Remove duplicate prose from memory files

---

## ADR-006: Unify Orchestration Paths

### Decision
Apply identical MCP tool scoping and solo/delegated prompt handling to both Ops-Hub worker and headless workflow scripts.

### Current Problem
Worker uses `toolsets.flags_for()` with `--strict-mcp-config`. Headless `workflows/_phase.sh` calls `claude --print` with all MCP servers enabled.

### Alternatives Considered
1. **Deprecate headless workflows** — Ops-Hub only
2. **Unify via _phase.sh calling worker** — shell invokes worker for each phase
3. **Add tool scoping to _phase.sh** — generate MCP config from toolsets.py
4. **Status quo** — accept divergence

### Chosen Approach
Option 3: `_phase.sh` generates `--mcp-config` from `toolsets.py` for each phase's job type equivalent.

### Why
- Headless mode is required for unattended server-side runs (per requirements)
- Tool scoping prevents pricing runs from using wrong tools (documented 32-failure incident)
- Single prompt source already shared via `python -m apps.worker.prompts`

### Tradeoffs
- Shell script becomes slightly more complex
- Must maintain phase-to-job-type mapping in shell

### Migration Impact
- Modify `workflows/_phase.sh` to call `toolsets.flags_for()`
- Add solo/delegated detection (check provider config or env var)
- Test each phase script with Ollama (solo) and subscription (delegated)

---

## ADR-007: Post-Claude Validation Gate (Keep, Improve)

### Decision
Retain post-Claude artifact validation before MongoDB sync. Add per-phase validation for autopilot runs.

### Current Problem
Validation runs once after full pipeline completes. Late failure wastes entire Claude pass.

### Alternatives Considered
1. **Remove validation** — trust Claude output
2. **Validate during Claude run** — PostToolUse hooks (partial, exists for extraction)
3. **Post-Claude only** — current approach
4. **Per-phase validation** — validate after each phase artifact write

### Chosen Approach
Option 4 for autopilot; keep option 3 for single-phase jobs.

### Why
- Validation caught 32 field contract failures in documented incident
- Per-phase validation in autopilot catches failures early
- Hooks provide real-time feedback but don't block all issues

### Tradeoffs
- Autopilot may still run later phases with earlier phase failures (unless gated)
- Additional validation calls add latency

### Migration Impact
- Modify `sync_results()` in worker to validate per phase in `run_full_pipeline`
- Consider aborting autopilot on critical validation failures

---

## ADR-008: Internal Token + Actor Auth Model

### Decision
Retain two-layer auth (NextAuth session + internal API token). Do not expose API directly to browser.

### Current Problem
Leaked `INTERNAL_API_TOKEN` allows full API access with spoofed `X-Actor`.

### Alternatives Considered
1. **JWT-based API auth** — browser calls API directly with user JWT
2. **mTLS between web and api** — certificate-based service auth
3. **Current proxy model** — Next.js adds internal token
4. **API Gateway** — AWS API Gateway with Cognito

### Chosen Approach
Option 3 with network isolation (ADR-004 companion). API not publicly reachable in production.

### Why
- Next.js proxy prevents token exposure to browser
- `X-Actor` set server-side from session (not spoofable from browser)
- Simple deployment model
- mTLS adds complexity not justified at current scale

### Tradeoffs
- Next.js is required proxy (single point)
- Direct API access for debugging requires network access
- Token leak still catastrophic if API port exposed

### Migration Impact
- Production compose: remove API port binding
- Document token rotation procedure
- Consider mTLS for future multi-region deployment

---

## ADR-009: MongoDB as Job Queue (No Redis/SQS)

### Decision
Keep MongoDB as the job queue. Do not add Redis, SQS, or dedicated queue service.

### Current Problem
Single worker poll loop; no distributed locking beyond atomic claim.

### Alternatives Considered
1. **Redis + Bull/Celery** — dedicated queue
2. **AWS SQS** — managed queue
3. **MongoDB (current)** — jobs collection with atomic claim
4. **PostgreSQL LISTEN/NOTIFY** — would require DB migration

### Chosen Approach
MongoDB with existing heartbeat/reaper/dedup mechanisms.

### Why
- Already working with 464 tests passing
- Atomic `find_one_and_update` claim is correct
- Exclusive job index prevents duplicate active jobs
- Adding Redis/SQS doubles infrastructure for no proven need

### Tradeoffs
- Poll-based (5s latency) not push-based
- Job queue queries add load to MongoDB (negligible at current volume)
- Horizontal scaling requires careful worker coordination (atomic claim handles this)

### Migration Impact
None. Document worker scaling: run N worker containers sharing projects volume.

---

## ADR-010: Filesystem + MongoDB Dual Store

### Decision
Retain dual storage: MongoDB for UI state, filesystem for agent artifacts. Do not move all artifacts to MongoDB or S3.

### Current Problem
Sync service bridges disk and MongoDB. Complexity in `sync.py`.

### Alternatives Considered
1. **MongoDB only** — store all artifacts as documents
2. **S3/object storage** — cloud-native artifact store
3. **Filesystem only** — no MongoDB for line items
4. **Dual store (current)** — MongoDB for UI, filesystem for agent workspace

### Chosen Approach
Option 4 with improved sync module boundaries.

### Why
- Claude Code expects filesystem workspace (`projects/{slug}/`)
- Skills and scripts reference file paths
- MongoDB enables fast UI queries without parsing JSON files
- PDF files must be on filesystem for pdf-tools MCP

### Tradeoffs
- Sync complexity and potential drift between disk and DB
- Shared volume required for multi-worker deployment
- Backup must cover both MongoDB and projects/

### Migration Impact
- Split sync.py for clarity (not eliminate)
- Add sync integrity checks (compare disk vs DB counts)
- Document backup procedure for both stores

---

## Decision Index

| ADR | Decision | Status |
|-----|----------|--------|
| ADR-001 | Modular monolith | Accepted |
| ADR-002 | PageIndex over RAG | Accepted |
| ADR-003 | 6 agents + 4 services | Proposed |
| ADR-004 | Accept skip-permissions + hooks | Accepted |
| ADR-005 | JSON canonical reference data | Proposed |
| ADR-006 | Unify orchestration paths | Proposed |
| ADR-007 | Per-phase validation | Proposed |
| ADR-008 | Internal token auth model | Accepted |
| ADR-009 | MongoDB job queue | Accepted |
| ADR-010 | Dual filesystem + MongoDB store | Accepted |
