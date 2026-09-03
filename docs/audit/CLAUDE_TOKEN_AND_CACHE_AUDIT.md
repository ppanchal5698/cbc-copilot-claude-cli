# Claude Token and Cache Audit

**Scope:** read-only audit of the agentic architecture, dated 2026-09-03, against
branch `remediation/audit-2026-09-02`.
**The audit itself modified nothing.** No code, config, prompt, Docker file,
database record or document was changed while it was carried out.

> ### Status: the backlog in this report has since been implemented.
>
> This document is kept as the **evidence and the reasoning**, not as an open
> to-do list. The findings table below carries a Status column; the 30/60/90 plan
> and the Implementation Backlog are the record of what was asked for, not of
> what is still outstanding. Re-measure with `cbc.services.runmetrics` before
> quoting any figure here as current — every number in this report predates the
> fixes.

**This audit is unusual in one respect: most of it is measured, not estimated.**
`projects/refactored_test/.runs/*.log` contains the CLI's own `--output-format
stream-json` output, including per-message `usage`, per-model `modelUsage` and
`total_cost_usd`. Nothing in the repository read those fields when this was
written; `cbc.services.runmetrics` does now. They are the evidentiary spine of
this report. Where a claim rests on inference instead, it is
labelled **likely** or **needs telemetry**.

---

## Executive Verdict

- **43–45% of every dollar a run costs is spent *writing* the prompt cache, not
  reasoning.** Measured across two real runs: cache-creation was $0.905 of $1.996
  (45.3%) and $0.544 of $1.259 (43.2%). The ~32,300-token static prefix is written to
  cache **ten times per run** — once per subagent context, plus re-writes when the
  5-minute ephemeral TTL expires across slow tool calls (`ephemeral_1h_input_tokens: 0`
  in both runs). This is the largest single cost line in the system and it buys nothing.

- **One whole model phase produces output that is provably thrown away.**
  `src/cbc/services/render.py` says so in its own docstring: *"whatever the agent wrote
  is overwritten by the validated render."* The worker re-renders `quotation.html` and
  `review_summary.html` deterministically after every pass. `quote-builder` is a
  subagent whose entire job is to shell out to a script the worker runs anyway.

- **89% of the tool-result bytes in the extraction run were four `Read` calls on
  200-DPI page renders** — 2,054,388 of 2,311,124 characters. A 36"×24" sheet at
  `dpi=200` is 7200×4800 px; the client downscales it to ≤1568 px before the model sees
  it, so a schedule row lands at roughly five pixels tall. That is expensive **and**
  illegible: the fix is an accuracy improvement, not only a cost one.

- **A single missing field re-runs an entire three-hour pipeline, up to three times,
  and the documented escape hatch is unreachable from any interface.**
  `validate_job_artifacts` raises, the worker marks the job retryable, and attempts 2–3
  hit the "Resume, do not redo" rule and read the same failing artifacts as finished
  work. `payload["force"]` exists in `prompts.py:463` and nothing anywhere sets it.

- **One line of code inflates every large tool result by ~60%.**
  `mcp-servers/_runtime.py:96` serialises every response from every server with
  `indent=2`. Measured on one `extract_tables` call: 419,629 chars pretty-printed vs
  168,068 compact.

- **The rendered-page cache is real, correct, content-keyed — and disabled by two
  independent bugs.** `pdfpages.page_image` computes the cache filename and then
  unconditionally re-renders (the `exists()` check lives only in the API module the MCP
  server never calls), and `/app/.cache` is not a Docker volume, so it is per-container
  and lost on rebuild.

- **Redis verdict — form A: "Do not add Redis now."** There is one worker running a
  serial `process()` loop, `container_name:` is set (which blocks `--scale`), no
  `replicas` are declared, and `WORKER_CONCURRENCY` is documented in `docs/scaling.md:20`
  but exists nowhere in the code. ADR-009 already decided this. Adding Redis would add
  an operational surface to a queue that handles one job at a time. Do the four
  no-regret fixes below first.

- **The system already has the telemetry it needs and does not read it.** Every
  `.runs/*.log` carries the numbers this audit is built on.
  `streaming.recording_warnings()` opens the file and looks only for warning strings.

- **Honest sizing.** The measured P0 set removes roughly **25–35% of per-run cost** and
  a much larger share of *worst-case* cost (the failed-validation triple-run). In
  absolute terms that is ≈$0.45 of a $1.63 average run, ≈$45 per 100 jobs. The larger
  prizes are latency, determinism, and being able to answer "what did that bid cost?"
  at all.

- **Recommended implementation order:** (1) compact MCP JSON, (2) fix the render-cache
  `exists()` check and mount `.cache` as a shared volume, (3) stop re-running whole
  jobs on validation failure, (4) delete the `quote-builder` phase, (5) ship the
  recording parser and start measuring, (6) crop-and-clamp page images, (7) everything
  else, gated on what the metrics then say.

---

## System Execution Map

```
 ESTIMATOR (browser)
      │  POST /api/documents  (multipart PDF)
      ▼
┌─────────────────────────── container: cbc-api ───────────────────────────┐
│ apps/api/routers/documents.py                                            │
│   storage.save_upload  →  ./projects/{slug}/uploads/raw/     [bind mount]│
│   apps/api/pipeline_jobs.py:24  →  cbc/services/jobs.py:40 enqueue()     │
│      dedup: EXCLUSIVE_JOB_TYPES only (jobs.py:71-80)                     │
│             + Mongo partial unique index (db.py:192-203)                 │
│             + COALESCE_BY_PAYLOAD = {"index_catalog": "filename"} only   │
│      NO content hash. NO idempotency key.                                │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │ insert {status:"queued", attempts:0}
                    ┌──────────────▼──────────────┐
                    │      MongoDB  `jobs`        │  ← SYSTEM OF RECORD
                    │  18 collections + pageIndex │    2 TTL indexes, both auth
                    └──────────────┬──────────────┘    NO TTL on jobs/auditLog
                                   │ poll every WORKER_POLL_SECONDS = 5
┌──────────────────────────────────▼──── container: cbc-worker ────────────┐
│ apps/worker/main.py:115 claim()  find_one_and_update, sort createdAt ASC │
│   SERIAL: `await process(job)` — one job at a time, one process, 1 replica│
│                                                                          │
│   main.py:597  read provider from db.settings (_id:"claude")             │
│   main.py:616  prompts.build(job, project, delegates=…)   1,4-2,2k tokens │
│   main.py:688  → cbc/core/claude_cli.py:106                              │
│                                                                          │
│   ┌───────────── CLAUDE CONTEXT BOUNDARY ────────────────────────────┐   │
│   │ claude --print --mcp-config <json> --strict-mcp-config           │   │
│   │        --disallowed-tools WebSearch WebFetch NotebookEdit        │   │
│   │        --dangerously-skip-permissions -- <prompt>                │   │
│   │                                                                  │   │
│   │  AUTO-LOADED, EVERY CONTEXT (orchestrator AND each subagent):    │   │
│   │    CLAUDE.md                        7,283 B                      │   │
│   │    @docs/cbc_process_flow.md        6,562 B                      │   │
│   │    .claude/rules/*.md  (8 files)   12,419 B                      │   │
│   │    = 26,264 B ≈ 6,600 tok  ── repo-controlled                    │   │
│   │    + CC system prompt + built-in tool schemas ── not controllable │   │
│   │    + MCP tool schemas (profile-scoped, 1.0–2.7k tok)             │   │
│   │    + 10 agent descriptions + 9 skill descriptions ≈ 2k tok       │   │
│   │    ────────────────────────────────────────────────────────────  │   │
│   │    MEASURED FIRST CACHE WRITE: 32,326 tokens                     │   │
│   │                                                                  │   │
│   │  ORCHESTRATOR ──Agent()──► subagent  ← NEW CONTEXT, prefix AGAIN │   │
│   │        (4 subagent streams in run A, 2 in run B)                 │   │
│   │                                                                  │   │
│   │  hooks: 2 PreToolUse + 1..3 PostToolUse python spawns PER CALL   │   │
│   └──────────┬───────────────────────────────────────────────────────┘   │
│              │ stdio                                                     │
│   ┌──────────▼─────────────────────────────────────────────────────┐     │
│   │ 5 MCP servers, one process each, 26 tools, 10,981 B of schema  │     │
│   │  pdf-tools 1.78s import │ catalog 2.05s │ calc 1.54s │ …       │     │
│   │  _runtime.py:96  json.dumps(payload, indent=2)  ← +60% bytes   │     │
│   └──────────┬─────────────────────────────────────────────────────┘     │
│              │                                                           │
│   writes ──► ./projects/{slug}/{extracted,priced,review}/*.json          │
│              ./projects/{slug}/.versions/{sha256}   ← content-addressed  │
│              ./projects/{slug}/.runs/{job}.log      ← 4 MB cap, HAS USAGE│
│              /app/.cache/pdf-pages/*.png            ← NOT A VOLUME       │
│                                                                          │
│   main.py:391 _sync_blocking_pre → validate_job_artifacts()              │
│        raises ValueError ──► finish(retryable) ──► WHOLE JOB RE-RUNS     │
│   main.py:402 _sync_blocking_render → render.py spawns 2 python procs    │
│        (one of which spawns a third)  ── OVERWRITES what the model wrote │
│   sync.import_extraction / import_quote_lines ──► MongoDB                │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
                            web/ (Next.js)  reads MongoDB via api

PERSISTENT STORES
  MongoDB            jobs, projects, lineItems, quoteLines, pageIndex, …  (durable)
  ./projects         bind-mounted rw into api AND worker                  (durable)
  ./pricebooks       rw on api, :ro on worker                             (durable)
  ./reference-library :ro on worker, not mounted on api                   (durable)
  /app/.cache        NO MOUNT — per-container, lost on rebuild            (EPHEMERAL)
```

---

## Token-Waste Findings

Ranked by expected value: cost reduction × quality gain ÷ (risk × effort).

| ID | Status | Severity | Evidence | Waste mechanism | Token category | Frequency | Accuracy risk | Recommended fix | Estimated impact |
|---|---|---|---|---|---|---|---|---|---|
| **T-01** | **Fixed** — `_runtime.py:35` uses `separators=(",", ":")` | **Critical** | `mcp-servers/_runtime.py:96` `json.dumps(payload, indent=2, default=str)`. Measured on one `extract_tables`: 419,629 chars vs 168,068 compact — **59.9% is indentation** | Every result from every server is pretty-printed. Whitespace enters the context, is cache-written once, then cache-read on every later turn of that conversation | Tool result → duplicate retrieval | Every tool call, every run | **None.** JSON semantics are identical | `separators=(",", ":")`. One line | ~40% of text tool-result tokens. Run A: ≈25,600 tok off cache-create ($0.10) + ≈500k off cache-read ($0.15) ≈ **12% of run cost** |
| **T-02** | **Fixed** — `quote-builder` gone from both prompts | **Critical** | `src/cbc/services/render.py` docstring: *"whatever the agent wrote is overwritten by the validated render"*; `apps/worker/main.py:402-408` `_sync_blocking_render`; `apps/worker/prompts.py:266,272` still delegate to `quote-builder` | A whole subagent context is spun up (full ~32k prefix cache-write + its own turns) to run a script the worker runs deterministically afterwards | Static prompt + output + retry | Every `build_proposal` and `run_full_pipeline` | **Improves.** Removes a path that can hand-write unvalidated HTML | Delete `quote-builder` from `BUILD_PROPOSAL`/`RUN_FULL_PIPELINE`; keep `quality-reviewer` for judgment prose only | 1 of 10 cold prefix writes + ~4-8 turns ≈ **8–12% of a proposal run** |
| **T-03** | **Fixed** — `ArtifactValidationError` → `permanent=True`, `main.py:896` | **Critical** | `src/cbc/validation/artifacts.py:537` raises → `apps/worker/main.py:301` `retryable = not ok and not permanent and attempts < MAX_ATTEMPTS`. `permanent` is never set on this path. `prompts.py:463` reads `payload["force"]`; **nothing in `web/`, `apps/api/`, `apps/worker/` sets it** | One missing `bbox` re-runs the entire job. `run_full_pipeline` = up to 3 × 3h sessions. Attempts 2–3 hit "Resume, do not redo" (`prompts.py:326-329`) and read the *same failing artifacts* as finished work | Retry / rerun | Every validation failure. `prompts.py:458-461` records it happening | **None.** Failing louder and sooner is strictly safer | Mark artifact-validation failure `permanent=True`, **or** set `payload["force"]=True` on requeue so attempt 2 rebuilds. Prefer a targeted `rerun_extraction` over a full pipeline | Up to **2× a full run cost per failed bid** (≈$4 on the measured runs). Needs telemetry to price the frequency |
| **T-04** | **Fixed** — `exists()` short-circuit + `cbc_cache` volume on api and worker | **High** | `src/cbc/core/pdfpages.py:127-128` — computes `_render_cache_name(...)` then unconditionally `doc[index].get_pixmap(dpi=dpi).save(output)`. The `if cached.exists(): return cached` lives only at `src/cbc/services/pdf.py:47`, which the MCP server never calls. `Dockerfile:57` creates `/app/.cache`; **no compose file mounts it** | Every `get_page_image` re-rasterises. The cache is also per-container and unshared between `api` and `worker`, contradicting the comment at `pdfpages.py:22-25`. `.cache/` is currently empty | Latency + duplicate retrieval | Every page render, in both processes | **None** | Add the `exists()` check to `pdfpages.page_image`; add `cbc_cache:/app/.cache` as a named volume on `api` and `worker`; key on file SHA-256 rather than `mtime_ns` | Removes 100% of repeat renders. Latency-dominant; feeds T-05's cache-TTL effect |
| **T-05** | **Fixed** — `region` param; DPI clamped to a 1568 px long edge | **High** | Recording run A: 4 × `Read` on `uploads/processed/*.png` = **2,054,388 of 2,311,124 tool-result chars (89%)**. Files are 7200×4800 px (`dpi=200` default, `mcp-servers/pdf-tools/server.py:291`). `get_page_image` has **no `region` parameter**; `extract_tables` does (`tools.py`, `region: array[number]`) | A whole architectural sheet is rendered at 200 DPI, then downscaled by the client to ≤1568 px. Schedule rows arrive ~5 px tall. The image then sits in context and is cache-read on every subsequent turn | Tool result + duplicate retrieval | Whenever a run falls back to vision | **Reduces risk.** A cropped region at readable resolution is strictly more legible than a downscaled full sheet | Add `region` to `get_page_image` (mirror `extract_tables`); clamp full-page renders so the long edge ≤1568 px unless a region is given; adopt the `MAX_DPI = 300` clamp already in `services/pdf.py:21` | 4 images ≈ 8,740 image tokens entering context, re-read ~40× ≈ 350k cache-read tokens ≈ **6% of run A**, plus 2 MB off the stdio path |
| **T-06** | **Partly** — subagent hops cut and the always-loaded context is 26,264 → 21,925 B; further trimming open | **High** | Measured: initial cache write **32,326 tokens**; **10 writes ≥8k tokens per run**, totalling 150,001 (run A) and 123,934 (run B). Repo-controlled share = `CLAUDE.md` 7,283 B + `@docs/cbc_process_flow.md` 6,562 B + 8 `.claude/rules/*.md` 12,419 B ≈ 6,600 tok ≈ **20% of the prefix** | Every subagent is a fresh context that re-writes the full prefix at $3.75/MTok, and the 5-minute ephemeral TTL (`ephemeral_1h_input_tokens: 0`) forces further re-writes across slow tool calls | Static prompt | Every context, every run | **Medium.** Rules are guardrails; cutting the wrong line weakens NFR-1/2/3. Cut prose, never constraints | Trim `docs/cbc_process_flow.md` (the `@`-inlined copy) to the phase table plus outputs; move the narrative to a path reference. Consolidate the seven copies of the margin bands (T-10). Reduce subagent hops (T-02) | 3,300 tok × 10 writes = 33,000 tok cache-create ($0.12) + ~165k cache-read ($0.05) ≈ **9% of run cost**, and it scales with subagent count |
| **T-07** | **Fixed** — signature-keyed `lru_cache` on loaders and the lite-kit table | **Medium** | `src/cbc/services/reference_library.py` — `load_margins:56`, `load_tax_rates:98`, `load_adders:132`, `load_finishes:258`, `load_frame_depths:298`, `load_stock_list:390` are all bare `json.loads(path.read_text())`. `depth_for_wall_type:451` is called **once per opening** from `sync_phases/geometry.py:166`. `core/calc.py:335` re-parses **193,218 B** of `lite_kit_prices.json` on every `lookup_lite_kit_list_price` call | Repeated disk reads and JSON parses inside hot loops and inside an MCP tool | Latency (no token cost) | Per opening / per tool call | **None** — the correct pattern already exists at `core/calc.py:83,110` (`@lru_cache` keyed on `_file_signature`) | Apply the existing `_file_signature` + `@lru_cache` pattern to every `reference_library.py` loader and to `lookup_lite_kit_list_price` | Latency only. Matters because latency drives T-06's cache-TTL re-writes |
| **T-08** | **Fixed** — projection + unfiltered-search guard on the MCP path | **Medium** | `src/cbc/pageindex/reader.py:87` `list(_collection().find(query).limit(50))` — *"Full documents, pages included"*, **no projection**, Pydantic-revalidated per call via `models.py:182-229`. Run B made **16** `find_pages` calls. The async twin refuses unfiltered >10-catalog searches (`query.py:206`); the MCP path has no such guard. `store.py:47-54` creates a `page_text` text index that nothing queries | Every catalog search pulls and revalidates up to 50 complete page-index documents | Latency (no token cost — the *response* is capped at `limit`, default 8, max 25) | Every pricing pass, many times | **None** | Add a projection; add the >10-catalog guard to the MCP path; either use the `page_text` index or drop it | Latency only, but 16× per pricing run. `pageindex/README.md` already says the shape fails around 50 catalogs |
| **T-09** | **Fixed** — one `pre_tool_use.py`, one `post_tool_use.py` | **Medium** | `.claude/settings.json` — `PreToolUse` fires `pre_send_quote.py` **and** `pre_delete_guard.py` (14,652 B) on both `Bash\|Write\|Edit\|MultiEdit\|NotebookEdit` and `mcp__.*`. `PostToolUse` adds `log_audit_trail.py`, plus `post_extraction_validate.py` (which spawns a **nested** `validate_project.py`, `post_extraction_validate.py:44-48`) and `post_quote_format.py` | 3 Python interpreter spawns per MCP tool call; 6 per write into `projects/` | Hidden operational overhead | Every tool call | **Must not be reduced.** These enforce NFR-1 and file safety and are the reason `--dangerously-skip-permissions` is acceptable | Keep every check. Merge the two `PreToolUse` scripts into one process and the three `PostToolUse` scripts into one; make `post_extraction_validate` import `check_extraction` rather than spawning a subprocess | 3 spawns → 2, and 6 → 2. Windows cold start ~150-400 ms each; on a 200-turn pipeline this is minutes of wall clock that feed T-06 |
| **T-10** | **Fixed** — seven literal sites down to two: the JSON source and `calc.py`'s documented fallback | **Medium** | The 27% commodity margin is a literal in **seven** places: `.claude/agents/pricing-engineer.md:65`, `.claude/memory/margin_sheet.md:7`, `.claude/skills/apply-margin/references/margin_bands.md:5,41`, `.claude/skills/apply-margin/SKILL.md:16`, `reference-library/margins/margin_framework.json:13`, `src/cbc/core/calc.py:35`, and `docs/cbc_process_flow.md:116` — the last is `@`-inlined into **every** context. `docs/audit/R4-004_reference_data.md:3`: *"Status: prepared, not applied."* | The same business constant is carried in context several times and can drift between copies | Static prompt + duplicate retrieval | Every context | **High if done carelessly.** `R4-004` verified all copies currently agree; a bad consolidation is how they stop agreeing | Keep `reference-library/*.json` as the single source (already loaded by `calc.py:83`). Reduce the prose copies to a one-line pointer. Do **not** touch `core/calc.py`'s `DEFAULT_BANDS` — it is a documented fallback | ~1,500 tok per context × 10 contexts ≈ 15,000 tok/run, plus it closes a real drift risk |
| **T-11** | **Fixed** — the guard blocks inline `fitz` (`test_hooks.py:103,120`) | **Medium** | Recording run A: **22 `Bash` calls**, one of them `python3 << 'EOF'\nimport fitz\n…` — exactly what `apps/worker/prompts.py:84-86` forbids (*"Do not open a PDF with `python -c \"import fitz ...\"`"*). Also 12 `Read` calls | The preamble spends ~1,200 tokens per context asking for behaviour it cannot enforce, and the behaviour happens anyway | Static prompt + output | Observed once; frequency unknown | **Medium.** A hand-rolled parser produces rows with no `bbox`, which is exactly what the validator then rejects (T-03) | Enforce rather than instruct: a `PreToolUse` hook that blocks `Bash` commands importing `fitz`/`pypdf` on paths under `uploads/raw/` or `pricebooks/`. Then shorten the preamble bullet to one line | Prevents the failure mode; ~200 tok/context of preamble reclaimed |
| **T-12** | **Fixed** — `text` dropped; `cell_boxes` kept for NFR-3 | **Low** | `src/cbc/core/pdfrows.py:177,179` — every row carries `cells` (list) and `text` (`" \| ".join(cells)`). Measured: 28,889 chars of exact duplication in one 4-page `extract_tables` call; `cell_boxes` was a further 81,838 chars (19.5%) | Identical word content shipped twice per row, plus per-cell geometry the caller rarely needs | Tool result | Every `extract_tables` | **Low, but real.** `cell_boxes` feeds bbox provenance (NFR-3) — drop `text`, keep `cell_boxes`, or make it opt-in | Drop `text` (derivable from `cells`); consider `include_cell_boxes: bool = True` so a caller that only needs the words can say so | ~7% of a table payload from `text` alone; up to 26% if `cell_boxes` becomes opt-in |
| **T-13** | **Open** — needs telemetry before acting, by design | **Low** | Recording run A: thinking tokens **19,065 of 42,237 output (45%)**; run B **9,950 of 36,147 (27.5%)**. Output is 31.7% / 43.1% of run cost | Extended thinking is on for every phase, including phases that are mostly mechanical file transformation | Output | Every run | **High.** Thinking is where the judgment on ambiguous schedules happens. Do not cut it on extraction or matching | Measure first (see Measurement Plan). If a per-phase thinking budget becomes configurable, consider reducing it only for `build_proposal` | Needs telemetry before acting. Listed so it is not mistaken for free |
| **T-14** | **Fixed** — coalesced on `fileSha`; `versions.py` routed through the gate | **Low** | `apps/api/routers/price_books.py:107` uses `storage.unique_filename`, so re-uploading identical bytes produces a new filename and bypasses `COALESCE_BY_PAYLOAD = {"index_catalog": "filename"}` (`services/jobs.py:37`). `apps/api/routers/versions.py:129` calls `jobs.enqueue` directly, bypassing the `pipeline_jobs.py:24` conflict gate | Duplicate `index_catalog` work on a byte-identical re-upload; `ingest_addendum` can be enqueued past the exclusivity check | Retry / rerun | Per re-upload | **None** | Coalesce on the file's SHA-256 rather than its name (`pageindex/store.py:22-28` already computes it); route `versions.py:129` through `enqueue_pipeline` | Removes a full catalog re-index per duplicate upload. `build.py:157-160` already skips the LLM call on an unchanged hash, so the waste is the job, not the model |
| **T-15** | **Fixed** — prompt-body parity and `--max-turns` on both scripts | **Low** | `workflows/_phase.sh:99` calls `python -m apps.worker.prompts "${project_dir}"` with no `--pipeline`, which returns `preamble_for()` **only**. `EXTRACT`'s "Start with `find_sheets` … Do not read the whole set" (`prompts.py:144-153`) and `MATCH_AND_PRICE`'s find_pages→extract_tables ladder (`prompts.py:201-215`) never reach the headless single-phase path. `test_headless_parity.py` checks tool scope, not prompt body | A terminal-launched phase gets none of the cost guidance the same phase gets through the worker. `_phase.sh:103` and `run_full_pipeline.sh:66` also omit `--max-turns` — the shell path is unbounded in turns | Static prompt + retry | Every headless phase run | **Medium.** The missing text is what stops a whole-set read | Have `_phase.sh` request the job template, not just the preamble; add `--max-turns` to both scripts; extend `test_headless_parity.py` to assert prompt-body parity | Prevents an unbounded whole-set read on the terminal path |
| **T-16** | **Fixed** — `scaling.md` and `architecture.md` refreshed | **Info** | `docs/scaling.md` cites `api/services/sync.py`, `api/routers/projects.py`, `api/deps.py` and `mcp-servers/pricebook/server.py` — **none exist**. Line 51 describes a per-process PDF text cache in a deleted server; `grep -rn "lru_cache" mcp-servers` returns zero. `docs/architecture.md:23,68` says 6 MCP servers; there are 5. Line 64 says 26 vendor files; `pricebooks/` has 16 | Stale docs cause an engineer to optimise a cache that does not exist | — | — | **None** | Refresh `docs/scaling.md` paths and the `architecture.md` counts as part of the first change that touches them | Prevents wasted work |

---

## Per-Phase Analysis

`src/cbc/core/toolsets.py:62-75` already scopes MCP servers per job type — a real and
already-shipped win (finding ORCH-001 / R3-006, closed). The columns below say what is
*left*.

### `extract_bid_set` / `rerun_extraction` / `ingest_addendum`

| | |
|---|---|
| **Exposed to Claude today** | Full ~32.3k prefix; the whole `uploads/raw/` tree; `pdf-tools` (6 tools) + `artifact-storage` (4); `Read`, `Write`, `Glob`, `Bash` |
| **Actually necessary** | The prompt; page numbers from one `find_sheets` call; `extract_tables` on the 2–3 sheets that scored; `parse_schedule.py` output. **Not** `Bash` for PDF work |
| **Outputs required** | `extracted/scope_metadata.json`, `scope_summary.json`, `door_schedule.json` (+ `frp_takeoff.json` when FRP is in scope), each opening carrying `source_page`, `bbox`, `page_size` |
| **Tools actually necessary** | `find_sheets`, `extract_tables`, `get_page_size`, `save_artifact`. `search_pdf` for spec scoping. `get_page_image` only as a fallback, and only cropped (T-05) |
| **Can be precomputed** | Sheet ranking (`find_sheets` is deterministic — cache it by file SHA); page text extraction (deterministic per SHA + extractor version); `parse_schedule.py` clustering; **`bbox` measurement, which the worker already redoes in Python at `sync_phases/geometry.py:24,41`**; frame-depth derivation (`geometry.py:134,155`) |
| **Retrieve on demand** | Individual page tables, page images |
| **Compact handoff artifact** | `extracted/_sheetmap.json` — `{file_sha, page → {kind, score, why}}` — written once by the orchestrator and handed to every subagent instead of each one re-searching. The prompt already asks for this in prose (`prompts.py:138-141`, `320-324`); make it a file |
| **Skip the model entirely?** | `find_sheets` ranking and `parse_schedule.py` are already deterministic — run them in the worker *before* the pass and put the result in the prompt. That removes 2–4 turns from every extraction |
| **Model tier** | Sonnet. This is the judgment-heavy phase: ambiguous schedules, handing, ratings. **Do not downgrade.** |

### `match_and_price`

| | |
|---|---|
| **Exposed today** | Full prefix; `catalog` (7) + `pdf-tools` (6) + `calc-engine` (6) + `p21-connector` (3) + `artifact-storage` (4) = 26 tools; `door_schedule.json`, `scope_summary.json` |
| **Actually necessary** | The confirmed schedule; the catalog page pointers; the vendor page the price is read off. Nothing from `uploads/raw/` — the prompt says so at `prompts.py:197-199` |
| **Outputs required** | `extracted/hardware_sets.json`; `priced/line_items.json` with the 17 fields listed at `prompts.py:226-229` |
| **Tools actually necessary** | `find_pages`, `get_multiplier`, `get_special_net`, `is_stock_item`, `extract_tables` (on the named page), `lookup_last_po`, `check_freshness`, `calculate_line`, `apply_margin`, `save_artifact` |
| **Can be precomputed** | Every `calc-engine` result — it is pure arithmetic over `reference-library/margins/margin_framework.json`. `validate_margin` and `compute_totals` need no model at all. Band assignment by division is already deterministic in `services/pricing.py:19-26` |
| **Retrieve on demand** | Catalog page hits, the price page itself |
| **Compact handoff artifact** | `priced/_costbasis.json` — `{part → {file_path, locator, pdf_page, basis, multiplier, effective_date}}` — so a re-price does not re-run `find_pages` for parts already located |
| **Skip the model entirely?** | Yes for the arithmetic: `compute_totals` is already re-run in Python by `scripts/validate_and_render_quote.py`. **Never** for the match decision or the read-the-price-off-the-page step — that is the whole design (`CLAUDE.md`, PageIndex section) |
| **Model tier** | Sonnet. Matching under NFR-2 is judgment. |

### `build_proposal`

| | |
|---|---|
| **Exposed today** | Full prefix; `calc-engine` + `artifact-storage`; three subagents — `quote-builder`, `quality-reviewer`, `delivery-agent` |
| **Actually necessary** | `priced/line_items.json` and the derived flags. That is all |
| **Outputs required** | `review/review_flags.json` prose, `review/quotation_email_draft.md`, `uploads/final/`. **Not** `quotation.html` or `review_summary.html` — the worker renders both |
| **Tools actually necessary** | `Read`, `Write`, `save_artifact`. `Bash` only for the delivery-agent's PDF attempt |
| **Can be precomputed** | `quotation.html` (`render.render_quotation`), `review_summary.html` (`render.render_review_summary`), and the mechanical flags (`validation/review.py:write_flags`) — **all three already are** |
| **Compact handoff artifact** | A `review/_flags_derived.json` summary — counts by severity plus the 20 worst lines — instead of handing the reviewer the whole `line_items.json` |
| **Skip the model entirely?** | **Yes for `quote-builder` — delete the phase (T-02).** Keep `quality-reviewer` for the RFI prose and judgment the deterministic flags cannot produce, and `delivery-agent` for the halt and the email draft |
| **Model tier** | Haiku is plausible for `delivery-agent` (template filling against a fixed structure). Note `services/provider.py:243-255` `_pin_model_aliases` currently collapses `sonnet`/`opus`/`haiku` onto one configured model on Bedrock/Cloudflare/Ollama, so per-phase tiering needs that pin relaxed first |

### `run_full_pipeline`

Everything above, in one session, with all five servers (`toolsets.py:60,63`) and
`PIPELINE_MAX_TURNS = 200`, `PIPELINE_TIMEOUT = 10800`. This is where the multipliers
bite: **9 subagent phases × the full prefix**. Removing `quote-builder` and folding the
sheet-map into a file are worth more here than anywhere else. `docs/headless_setup.md:146-155`
records a full run at ~7m36s; the measured recordings run 9–14 minutes of API time,
comfortably past several 5-minute cache windows.

### `ingest_pricebook`

| | |
|---|---|
| **Exposed today** | Full prefix; `catalog` + `pdf-tools` + `artifact-storage` |
| **Skip the model entirely?** | Partly. `index_catalog` is **already** a `LOCAL_HANDLERS` job with no Claude pass (`apps/worker/main.py:508-511`) — the right pattern, already applied. `ingest_pricebook` still needs a model to read irregular vendor layouts |
| **Note** | `build.py:157-160` already skips the whole LLM pass when the file SHA is unchanged. This is the best cache in the repository and the template for the rest |

---

## Cache Design

Ordered by value ÷ effort. **No cache below reuses a value without a dependency hash.**

| Cache | Problem solved | Key | Storage | Invalidation | TTL | Audit/provenance | Expected token savings | Expected latency savings | Complexity |
|---|---|---|---|---|---|---|---|---|---|
| **C-01 Page render** | `pdfpages.page_image:128` always re-rasterises; `/app/.cache` is per-container | `sha256(file bytes) + page + dpi + region + renderer_version` | Named Docker volume `cbc_cache:/app/.cache/pdf-pages`, shared by `api` + `worker` | New file SHA, or `renderer_version` bump | None; LRU prune by total bytes | Manifest sidecar records source SHA, page, dpi, PyMuPDF version, rendered_at | 0 direct (path-returning tool) — but removes repeat *renders* that push runs past the 5-min cache window | **High.** A 36"×24" render is seconds; both processes currently redo it | **Low** |
| **C-02 PDF text / table extraction** | `find_sheets` and `search_pdf` call `get_text()` on **every page**, every call (`pdf-tools/server.py`, no caching anywhere) | `sha256(file) + page_range + extractor_version + options` | Same volume, JSON per key; or SQLite `.cache/pdftext.db` keyed by the same tuple | New file SHA or extractor version | None | Key encodes extractor version; store `extracted_at` | Enables T-01/T-12 payload shaping to be computed once | **High** — repeated `search_pdf` over a 744-page set is the dominant PDF cost | **Low** |
| **C-03 Sheet map (page classification)** | Four subagents each re-search the same set; the prompt asks them not to in prose (`prompts.py:138-141`) | `sha256(file) + query_terms + classifier_version` | `projects/{slug}/extracted/_sheetmap.json`, project-scoped | New upload SHA, or terms change | None; regenerated per bid | Records source SHA, terms, generated_at, per-page `why` | ~1,300 tok × (subagents − 1) per file, plus the turns | Removes 3+ `find_sheets` round trips per run | **Low** |
| **C-04 Reference-library loads** | `reference_library.py` re-reads and re-parses on every call; `lookup_lite_kit_list_price` re-parses 193 KB per tool call | `_file_signature = (st_mtime_ns, st_size)` — the pattern already at `core/calc.py:80-83` | In-process `@lru_cache(maxsize=4)` | File mtime/size change | Process lifetime | The file itself remains the source of truth; nothing is copied | 0 | Removes a 193 KB parse per `calc-engine` call and a JSON parse per opening | **Low** |
| **C-05 Job idempotency / dedup** | Byte-identical re-upload re-indexes (T-14); `versions.py:129` bypasses the conflict gate | `sha256(payload canonical JSON) + job_type + projectId` stored as `idempotencyKey` | MongoDB `jobs`, **partial unique index** on `{idempotencyKey}` where `status ∈ {queued, running}` — same shape as the existing `exclusive_active_job` index (`db.py:192-203`) | Terminal job status releases the key | Optional TTL index on a `dedupUntil` field | The job document *is* the audit record; `auditLog` already records every transition | Removes whole duplicate runs | Removes whole duplicate runs | **Low** |
| **C-06 Deterministic calc results** | `calc-engine` recomputes pure arithmetic per line | `sha256(cost, margin, quantity, product_type, bands_signature)` | In-process `@lru_cache` in `core/calc.py` | `margin_framework.json` signature change (already tracked at `calc.py:80`) | Process lifetime | Bands signature is part of the key, so a margin-sheet edit invalidates | 0 | Marginal — arithmetic is cheap. Listed because the *key design* is the model for C-08 | **Low** |
| **C-07 Catalog page-search results** | `reader.all_catalogs` refetches ≤50 full documents per `find_pages`; 16 calls in one pricing run (T-08) | `normalized_query + vendor + limit + max(pageIndex.builtAt for matching catalogs)` | In-process LRU in the `catalog` MCP process, `maxsize=256` | Any `pageIndex` document's `builtAt` advancing — cheap to check with one projected query | Process lifetime (a server process is one job) | Result records the `builtAt` watermark it was computed against | 0 (responses are already capped at `limit`) | 16 × (50-document fetch + Pydantic revalidation) → 1 | **Medium** |
| **C-08 Product-match decisions** | A re-price re-decides matches that nothing invalidated | `sha256(specified_part, attributes) + catalog_builtAt_watermark + matcher_prompt_version` | `projects/{slug}/extracted/_matchcache.json`, **project-scoped only** | Any dependency hash changing; **always invalidated on a `force` run** | None | Each entry stores confidence, the `why`, and every dependency hash. **Entries below 0.75 confidence are never reused** — NFR-2 says a flagged match needs a human, and a cache must not launder that into a settled fact | Avoids re-running matching on a pricing-only rerun | Whole phase on a partial rerun | **High** |
| **C-09 Rendered quote** | `render_quotation` runs on every `build_proposal` even when nothing changed | `sha256(canonical line_items.json) + template_sha + renderer_version` | `projects/{slug}/.versions/` — the content-addressed store that **already exists** (`artifact-storage/server.py:26,75`) | Any input hash change | None | `.versions/versions.jsonl` is already the manifest | 0 | Skips two subprocess spawns when nothing changed | **Low** |
| **C-10 Prompt-fragment snapshot** | No way to attribute a cost change to a prompt change | `sha256` of `CLAUDE.md`, each rule, each agent, each skill, the job template | MongoDB `runMetrics.contextHashes` (see Measurement Plan) | N/A — recorded, not reused | N/A | This *is* provenance: it answers "which prompt produced this quote?" | 0 | 0 | **Low** |
| **C-11 Retry / partial-completion state** | A retry re-runs everything (T-03) | `jobId + attempt`, listing each phase output path with its SHA at the moment it validated | MongoDB `jobs.phaseState` | Cleared on a `force` run | Job lifetime | Each phase records the artifact SHA it produced and whether it passed validation | Turns a 3× full rerun into a targeted rerun of the failing phase | Hours on a failed pipeline | **High** |

### Canonical content-addressed artifact design

The repository already has two-thirds of this. `artifact-storage/server.py:26,75` writes
`projects/{slug}/.versions/{sha256}` and appends to `versions.jsonl`, and
`pageindex/store.py:22-28` computes a real content SHA and uses it to skip work
(`build.py:157-160`). What is missing is a **dependency manifest** — the artifact
records its own hash but not the hashes of everything it was derived from, so nothing
can decide whether it is still valid.

Proposed manifest, one per derived artifact, written beside it as `<name>.manifest.json`:

```json
{
  "artifact": "extracted/door_schedule.json",
  "artifactSha256": "9f2c…",
  "producedBy": { "jobId": "6a983a6a252290d4e1b0dc59", "jobType": "extract_bid_set", "attempt": 1 },
  "producedAt": "2026-09-02T18:41:07Z",
  "inputs": [
    { "kind": "source_pdf", "path": "uploads/raw/01_DTGO Prototype_ARCHITECTURAL.pdf",
      "sha256": "c41b…", "pages": [12, 13] }
  ],
  "dependencies": {
    "parserVersion":      "parse_schedule@2026-08-30",
    "rendererVersion":    "pymupdf-1.24.9",
    "promptSha256":       "3ab9…",
    "claudeMdSha256":     "77d0…",
    "rulesSha256":        "b1e4…",
    "agentSha256":        { "takeoff-engineer": "5cc2…" },
    "referenceDataSha256":{ "margin_framework.json": "0d81…", "wall_type_to_depth.json": "aa19…" },
    "model":              "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
  },
  "validation": { "passed": true, "checkedBy": "check_extraction", "at": "2026-09-02T18:41:09Z" }
}
```

**Reuse rule — the whole point of the manifest:** a cached artifact may be reused only
when **every** hash in `dependencies` matches the current value **and**
`validation.passed` is `true`. Any mismatch, or an absent manifest, means recompute.
There is no partial credit and no staleness window: a price sheet that changed, a rule
that was edited, or a model that was swapped all invalidate the artifact that was
derived under the old one. This is what makes the caches above safe under NFR-3 —
"where did this number come from?" is answerable from the manifest alone, months later.

---

## Redis Decision

### Current-state assessment

| Question | Evidence | Answer |
|---|---|---|
| Worker count | `docker-compose.yml:129-159` — one `worker` service, `container_name: cbc-worker` (which forbids `--scale`), **no `deploy:`, no `replicas`, no resource limits** | 1 |
| Concurrency model | `apps/worker/main.py:825-849` — `await process(job)` inside the poll loop | Strictly serial, one job at a time |
| `WORKER_CONCURRENCY` | Documented at `docs/scaling.md:20`; `grep` across `apps/`, `src/` returns nothing | Does not exist |
| Queue behaviour | `main.py:115-135` atomic `find_one_and_update`, `sort=[("createdAt", 1)]`; indexes `status+createdAt`, `status+heartbeatAt`, partial-unique `exclusive_active_job` (`db.py:190-204`) | Correct, atomic, indexed |
| Enqueue latency | `WORKER_POLL_SECONDS = 5` | 5 s worst case, against jobs that run 9 minutes to 3 hours |
| Does the cache need to survive restarts? | The render cache should (C-01). It is derived data whose recomputation costs seconds | Yes — but a **volume** satisfies that, not a server |
| Cross-container sharing needed? | `api` and `worker` both render pages | Yes — `./projects` and a `cbc_cache` volume satisfy it |
| Ephemeral coordination or auditable artifact? | Everything the caches hold is either derived-and-recomputable (renders, text) or business evidence (line items, flags, manifests) | **Neither is a Redis workload** |
| Prior decision | `docs/audit/ARCHITECTURAL_DECISIONS.md:281-302`, ADR-009: *"Keep MongoDB as the job queue. Do not add Redis, SQS, or dedicated queue service."* | Already decided, and still right |

### Recommended decision

> ## **A. "Do not add Redis now. Use a shared Docker volume, MongoDB indexes, and in-process LRU first."**

A 5-second enqueue latency against a job that runs for 9–180 minutes is 0.05–0.9% of
wall clock. Redis would replace a correct, atomic, already-indexed queue with a second
datastore to secure, monitor, back up and reason about during a failure — for a
throughput problem that does not exist, on a worker that processes one job at a time.

Every cache in this report is served better by something already present:

| Need | Use | Not Redis, because |
|---|---|---|
| Rendered pages shared across containers, surviving restarts | Named Docker volume + content-addressed filenames (C-01) | These are megabyte PNG blobs; a shared filesystem is the natural store and the code already targets one |
| PDF text / table extraction (C-02) | Same volume, or SQLite at `.cache/pdftext.db` | Structured, queryable, single-writer, zero ops |
| Job dedup (C-05) | MongoDB partial unique index — the exact pattern already at `db.py:192-203` | The uniqueness guarantee must be transactional with the job insert. A separate store makes that two-phase and racy |
| Catalog search results (C-07) | In-process LRU in the `catalog` MCP process | One MCP process serves one job; there is nothing to share |
| Reference-library loads (C-04) | `@lru_cache` keyed on file signature — already the pattern at `core/calc.py:83` | Reading a 1.6 KB local file is faster than a network round trip |
| Match decisions, manifests, flags (C-08–C-10) | Project filesystem + `.versions/` + MongoDB | **Audit evidence under NFR-3.** It must be durable, versioned and inspectable. Redis is the wrong home for anything an estimator may have to defend in six months |

### What must stay in MongoDB / the filesystem, unconditionally

Canonical bid and project data; every priced line and its cost basis; `audit_trail.jsonl`
and the `auditLog` collection; `.versions/` artifacts and their manifests; the
`pageIndex` documents; the `jobs` collection as the queue of record. None of these may
live in a cache of any kind.

### Do these first (all cheaper than Redis, all reversible)

1. Mount `cbc_cache:/app/.cache` on `api` and `worker` (C-01, T-04) — **one compose stanza**.
2. Add the `exists()` check to `pdfpages.page_image` (T-04) — **three lines**.
3. `@lru_cache` the `reference_library.py` loaders and `lookup_lite_kit_list_price` (C-04).
4. Add the `idempotencyKey` partial unique index (C-05).

### If Redis ever becomes justified

The trigger is **queue depth**, not cost: sustained enqueue-to-start latency above ~30 s
with more than one worker actually running. That requires `WORKER_CONCURRENCY` to exist,
`container_name:` to be removed, and `./projects` to be on shared storage
(`docs/scaling.md:25-27`) — three prerequisites that are not met. Revisit only when the
`runMetrics` collection shows it.

### Operational risks and rollback plan

If Redis is ever added: it must hold **only** ephemeral coordination (a lease, a
rate-limit counter, a pub/sub wake-up), never a business artifact; it must be treated as
a cold-start-able cache so that flushing it degrades latency and never correctness; and
rollback must be a single config flag returning the worker to the poll loop, with no
data migration. If any of those three cannot be honoured, the workload does not belong
in Redis.

---

## Target Architecture

```
                    ┌──────────────────────────────────────────────┐
                    │  DETERMINISTIC PRE-PASS  (Python, no model)  │
                    │                                              │
   upload ─────────►│  1. sha256(file)                             │
                    │  2. C-02 text/table cache  ── hit? reuse     │
                    │  3. find_sheets ranking    ── deterministic  │
                    │  4. parse_schedule.py      ── deterministic  │
                    │  5. write extracted/_sheetmap.json           │
                    └───────────────────┬──────────────────────────┘
                                        │ compact handoff, ~1-2 KB
     ══════════════════ CLAUDE CONTEXT BOUNDARY ══════════════════════
                                        ▼
   WHAT CLAUDE RECEIVES FOR A PHASE          WHAT IT NEVER RECEIVES
   ─────────────────────────────────         UNLESS IT ASKS
   • trimmed CLAUDE.md + rules               ✗ any raw PDF
   • the job template (1.4-2.2k tok)         ✗ whole-set extract_tables
   • extracted/_sheetmap.json                ✗ full-sheet 200-DPI images
   • the prior phase's compact artifact      ✗ the reference-library JSON
   • ONLY that phase's MCP servers           ✗ price-book PDFs
     (toolsets.py — already shipped)         ✗ prior run logs / recordings
                                             ✗ the audit trail
                                        │
              ┌─────────────────────────┼──────────────────────────┐
              ▼                         ▼                          ▼
      ┌───────────────┐        ┌────────────────┐        ┌──────────────────┐
      │ take-off      │        │ match + price  │        │ review + deliver │
      │ pdf-tools     │        │ catalog        │        │ artifact-storage │
      │ artifact-stor │        │ pdf-tools      │        │ (Bash for PDF)   │
      │ MODEL: judgment│       │ calc-engine    │        │ MODEL: RFI prose │
      │  on ambiguous  │       │ p21-connector  │        │  + the halt      │
      │  schedules     │       │ MODEL: match + │        │                  │
      │                │       │  read the page │        │  ✗ quote-builder │
      └───────┬────────┘       └───────┬────────┘        │    DELETED (T-02)│
              │                        │                 └────────┬─────────┘
              │  every tool call:      │                          │
              │  ┌──────────────────────────────────────┐         │
              │  │ CACHE LOOKUP BEFORE EXPENSIVE WORK   │         │
              │  │  render?  C-01 sha+page+dpi+region   │         │
              │  │  text?    C-02 sha+extractor_version │         │
              │  │  catalog? C-07 query+builtAt         │         │
              │  │  match?   C-08 +every dep hash,      │         │
              │  │            and only when conf ≥0.75  │         │
              │  │  miss → compute → write → manifest   │         │
              │  └──────────────────────────────────────┘         │
              ▼                        ▼                          ▼
     ══════════════════ CLAUDE CONTEXT BOUNDARY ══════════════════════
                                        │
                    ┌───────────────────▼──────────────────────────┐
                    │  MODEL-FREE DETERMINISTIC PATHWAYS           │
                    │   (all of these already exist in Python)     │
                    │                                              │
                    │  sync.measure_bboxes      geometry.py:24     │
                    │  sync.derive_frame_depths geometry.py:134    │
                    │  validate_job_artifacts   artifacts.py:510   │
                    │      ──► PER-PHASE GATE, not one end gate    │
                    │      ──► failure = permanent OR force-requeue│
                    │  review.write_flags       review.py          │
                    │  render_quotation         render.py:70       │
                    │  render_review_summary    render.py:75       │
                    │  calc.* (margins, tax, totals)  core/calc.py │
                    └───────────────────┬──────────────────────────┘
                                        ▼
                    ┌──────────────────────────────────────────────┐
                    │  MANIFEST + TELEMETRY                        │
                    │   <artifact>.manifest.json  (dep hashes)     │
                    │   MongoDB runMetrics  ← parsed from .runs/   │
                    └──────────────────────────────────────────────┘
```

---

## 30/60/90-Day Plan

### 0–7 days — no-regret, low-risk

| # | Change | Files | Why now |
|---|---|---|---|
| 1 | Compact MCP JSON: `separators=(",", ":")` | `mcp-servers/_runtime.py:96` | One line, ~40% off text tool results, zero semantic change |
| 2 | Render-cache `exists()` check | `src/cbc/core/pdfpages.py:127-128` | Three lines; the cache already exists and is bypassed |
| 3 | Mount `cbc_cache:/app/.cache` on `api` and `worker` | `docker-compose.yml`, `docker-compose.override.yml` | One stanza; makes (2) actually persist and be shared |
| 4 | Artifact-validation failure → `permanent=True` (or set `payload["force"]` on requeue) | `apps/worker/main.py:793-798` | Stops the 3× full-pipeline rerun (T-03) |
| 5 | Delete `quote-builder` from the proposal and pipeline prompts | `apps/worker/prompts.py:266,345`, `DELEGATION_RULE:25-27`, `tests/api/test_autopilot.py:64-75` | Its output is provably discarded (T-02) |
| 6 | `@lru_cache` on `reference_library.py` loaders + `lookup_lite_kit_list_price` | `src/cbc/services/reference_library.py`, `src/cbc/core/calc.py:335` | Copy the pattern from `calc.py:83`; removes a 193 KB parse per tool call |
| 7 | Refresh the stale paths in `docs/scaling.md` and the counts in `docs/architecture.md` | those two files | Stops the next engineer optimising a deleted server (T-16) |

### 8–30 days — instrumentation and structure

| # | Change | Why |
|---|---|---|
| 8 | **Recording parser → `runMetrics` collection.** Parse `.runs/*.log` for `modelUsage`, `total_cost_usd`, `duration_api_ms`, per-message `usage`, tool-call counts | The data already exists. Until this ships, every number after item 7 is an estimate |
| 9 | Backfill `runMetrics` from existing recordings | Establishes a baseline before any prompt change |
| 10 | Context-hash recording (C-10) on every run | Makes "which prompt change moved the cost?" answerable |
| 11 | `region` param on `get_page_image` + long-edge clamp to 1568 px | T-05: accuracy *and* cost |
| 12 | Projection + >10-catalog guard on the MCP `find_pages` path | T-08 |
| 13 | Merge the hook scripts: 2 PreToolUse → 1, 3 PostToolUse → 1; make `post_extraction_validate` import rather than spawn | T-09. **Every check preserved** |
| 14 | Drop `text` from `extract_tables` rows; make `cell_boxes` opt-in | T-12 |
| 15 | Job `idempotencyKey` partial unique index (C-05); route `versions.py:129` through `enqueue_pipeline` | T-14 |

### 31–60 days — cache and workflow refactoring

| # | Change | Why |
|---|---|---|
| 16 | C-02 PDF text/table cache keyed on file SHA + extractor version | The largest remaining repeated work |
| 17 | Deterministic pre-pass: run `find_sheets` and `parse_schedule.py` in the worker, write `extracted/_sheetmap.json`, hand it to the prompt | Removes 2–4 turns per extraction and makes the "find the sheets once" rule structural instead of hoped-for |
| 18 | Artifact manifests with full dependency hashes | Precondition for every reuse decision |
| 19 | Per-phase validation gates (ADR-007, still "Proposed") | Fail at the end of take-off, not after pricing |
| 20 | C-11 `jobs.phaseState` — targeted reruns | Turns a 3-hour rerun into a 20-minute one |
| 21 | Trim the `@`-inlined `docs/cbc_process_flow.md` to its table; consolidate the seven margin-band copies (T-06, T-10) | Multiplied by every context. Do it **after** item 8 so the effect is measurable |

### 61–90 days — scaling, only if the metrics justify it

| # | Change | Gate |
|---|---|---|
| 22 | C-07 catalog search LRU | `runMetrics` shows `find_pages` latency material |
| 23 | C-08 match-decision cache, confidence-gated at 0.75 | Only after manifests (18) exist |
| 24 | Per-phase model tiers (relax `_pin_model_aliases`) | Only if `runMetrics` shows a phase whose output is mechanical |
| 25 | `WORKER_CONCURRENCY` + remove `container_name:` + shared `./projects` storage | Sustained queue depth > 1 |
| 26 | **Redis — still not recommended.** Revisit only if enqueue-to-start latency exceeds ~30 s with multiple workers actually running | 25 must ship first, and the metric must be observed, not assumed |

---

## Implementation Backlog

### P0

**B-01 — Compact MCP tool results**
Files: `mcp-servers/_runtime.py:96`.
Acceptance: a large `extract_tables` response is ≥35% smaller; all field values byte-identical after `json.loads`.
Tests: extend `tests/pipeline/test_workflow_cost.py:137-146` (the existing `< 400_000` budget) with a tighter ceiling; add a round-trip equality assertion.
Rollback: revert one line.
Metric: `runMetrics.toolResultChars` p50 and p95.

**B-02 — Rendered-page cache actually caches**
Files: `src/cbc/core/pdfpages.py:113-136`; `docker-compose.yml`, `docker-compose.override.yml`; optionally `src/cbc/services/pdf.py:41-48` to converge on one key function.
Acceptance: two identical `get_page_image` calls produce one `get_pixmap`; the PNG survives `docker compose up --build`; `api` and `worker` see the same file. Key switches from `mtime_ns` to content SHA-256.
Tests: new `tests/pipeline/test_render_cache.py` — call twice, assert one render (monkeypatch `get_pixmap`); assert the cache path is under `RENDER_CACHE` and never under `uploads/raw/` (the `_writable_target` guards at `pdfpages.py:65-102` must keep passing).
Rollback: revert; the volume is additive and harmless.
Metric: render count per job; `runMetrics.durationApiMs`.

**B-03 — A validation failure must not re-run the whole job**
Files: `apps/worker/main.py:793-798` and `finish()` at `:300-302`; `src/cbc/validation/artifacts.py:537`.
Acceptance: an artifact-validation failure ends the job at attempt 1 with the problem list in `job.error`; **or**, if requeued, attempt 2 carries `payload["force"]=True` and the prompt shows the forced-clean-run block (`prompts.py:463-470`).
Tests: extend `tests/api/test_recovery.py` — assert `attempts == 1` and `status == "failed"` after a validation failure, or that attempt 2's rendered prompt contains "This IS a forced clean run".
Rollback: revert the `permanent` flag.
Metric: attempts-per-job distribution; total cost attributable to attempts > 1.

**B-04 — Delete the `quote-builder` phase**
Files: `apps/worker/prompts.py` (`BUILD_PROPOSAL:266`, `RUN_FULL_PIPELINE:345`, `DELEGATION_RULE:25-27`); `tests/api/test_autopilot.py:64-75`; `tests/pipeline/test_agent_definitions.py:79-97`; decide whether `.claude/agents/quote-builder.md` is deleted or retained for the headless `phase6_deliver.sh` path.
Acceptance: `build_proposal` and `run_full_pipeline` still produce `quotation.html`, `review_summary.html`, `review_flags.json`, `quotation_email_draft.md` and `uploads/final/`; one fewer subagent stream in the recording.
Tests: the two above must be updated in the same commit — `test_the_pipeline_prompt_names_every_subagent` currently pins all nine names and asserts each file exists. `tests/pipeline/test_render_service.py` must still pass unchanged.
Rollback: revert the prompt edit.
Metric: subagent stream count and cache-creation tokens per `build_proposal`.

**B-05 — Reference-library read caching**
Files: `src/cbc/services/reference_library.py` (all eight loaders); `src/cbc/core/calc.py:335`.
Acceptance: `load_frame_depths` reads the file once per unchanged-file process; editing the JSON is picked up on the next call.
Tests: new — call twice with a patched `read_text` counter; then bump mtime and assert a re-read.
Rollback: remove the decorators.
Metric: `derive_frame_depths` wall time on a 200-opening bid.

### P1

**B-06 — Recording parser → `runMetrics`**
Files: new `src/cbc/services/runmetrics.py`; called from `apps/worker/main.py` after `finish()`; new collection + indexes in `src/cbc/db.py`.
Acceptance: every completed job writes one `runMetrics` document (shape below); a backfill script populates it from existing `.runs/*.log`.
Tests: parse the two committed recordings and assert `totalCostUsd == 1.9990174` and `1.2621052500000003`.
Rollback: drop the collection; nothing else reads it yet.
Metric: this *is* the metric.

**B-07 — `region` + DPI clamp on `get_page_image`**
Files: `mcp-servers/pdf-tools/server.py:288-294`, `tools.py:79-99`, `src/cbc/core/pdfpages.py:113-136`.
Acceptance: `region` crops as `extract_tables` does; a full-page render clamps the long edge to 1568 px; a region render may exceed it. Fix the wrong output directory in the description at `tools.py:82-83`.
Tests: assert a full-page render of the 2592×1728 pt fixture is ≤1568 px on the long edge; assert a region render returns the requested crop.
Rollback: revert; existing calls keep working (`region` is optional).
Metric: image bytes per run; extraction accuracy on the scoring fixture (`scripts/score_extraction.py`).

**B-08 — Hook consolidation**
Files: `.claude/settings.json`; `.claude/hooks/*.py`.
Acceptance: one `PreToolUse` process and one `PostToolUse` process per tool call. **Every existing check still runs and still blocks.** `post_extraction_validate` imports `cbc.validation.check_extraction` instead of spawning `validate_project.py`.
Tests: `tests/pipeline/test_hooks.py` must pass unchanged; add a case asserting a blocked send still exits 2 and a blocked delete still exits 2.
Rollback: restore the previous `settings.json`.
Metric: mean inter-tool-call gap from `runMetrics`.

**B-09 — Job idempotency key**
Files: `src/cbc/services/jobs.py:40-111`, `src/cbc/db.py:190-204`, `apps/api/routers/price_books.py:107,132`, `apps/api/routers/versions.py:129`.
Acceptance: two byte-identical price-book uploads produce one `index_catalog` job; a changed file still produces a second.
Tests: `tests/api/test_recovery.py:344-379` already asserts the name-based behaviour — extend it to SHA-based.
Rollback: drop the index; `enqueue` falls back to current behaviour.
Metric: duplicate-job rate.

**B-10 — Fix the schema/implementation mismatches in `pdf-tools`**
Files: `mcp-servers/pdf-tools/tools.py:79-130`, `server.py:30,92,163,298`.
Acceptance: `context_chars` default agrees between schema (500) and implementation (160); `max_pages` and `max_hits` appear in the schemas so the documented escape hatch is reachable; the unreachable `MAX_HITS = 200` is either wired up or removed.
Tests: a schema-vs-signature parity test across all 26 tools.
Rollback: revert.
Metric: none — this is a correctness fix that removes a class of wasted retry.

### P2

**B-11** Deterministic pre-pass writing `extracted/_sheetmap.json` — `apps/worker/main.py`, `src/cbc/services/`, `apps/worker/prompts.py:138-141,320-324`.
**B-12** C-02 PDF text/table cache — `src/cbc/core/pdfpages.py`, `pdfrows.py`, new `.cache/pdftext.db`.
**B-13** Artifact manifests — `mcp-servers/artifact-storage/server.py:63-95`, `src/cbc/services/storage.py`.
**B-14** Per-phase validation gates (ADR-007) — `src/cbc/validation/artifacts.py:495-506`, `apps/worker/main.py:391-398`.
**B-15** `jobs.phaseState` targeted reruns — `apps/worker/main.py`, `src/cbc/services/jobs.py`.
**B-16** Consolidate the seven margin-band copies (T-10) — `.claude/**`, `docs/cbc_process_flow.md:116`. **Leave `core/calc.py:35` `DEFAULT_BANDS` alone**; it is the documented fallback.
**B-17** `_phase.sh` prompt-body parity + `--max-turns` (T-15) — `workflows/_phase.sh:99,103`, `run_full_pipeline.sh:66`, `tests/pipeline/test_headless_parity.py`. Note that test regex-parses `job_type_for()`'s shape.

---

## Measurement Plan

**Nothing in this plan requires new instrumentation in the model path.** The CLI already
emits everything below in `--output-format stream-json`, and
`src/cbc/core/streaming.py` already captures it to `projects/{slug}/.runs/{job}.log`
(4 MB cap, credentials redacted on the way in). The gap is that only
`recording_warnings()` reads it, and only for warning strings.

### Per-run telemetry — `runMetrics` collection

```json
{
  "_id":        "6a983a6a252290d4e1b0dc59:1",
  "jobId":      "6a983a6a252290d4e1b0dc59",
  "attempt":    1,
  "projectId":  "…",
  "projectSlug":"refactored_test",
  "jobType":    "extract_bid_set",
  "phase":      "extraction",

  "provider":   { "mode": "bedrock", "region": "ap-south-1" },
  "sessionId":  "e4af4a1a-3db4-4ce4-b7af-4f29feb479ba",
  "startedAt":  "2026-09-02T18:27:44Z",
  "finishedAt": "2026-09-02T18:41:23Z",
  "durationApiMs": 818643,

  "tokens": {
    "input": 614, "output": 42237, "thinking": 19065,
    "cacheCreate": 241256, "cacheRead": 1520848,
    "coldPrefixWrites": 10, "coldPrefixTokens": 150001,
    "largestSinglePrefixWrite": 32326
  },
  "modelUsage": {
    "global.anthropic.claude-sonnet-4-5-20250929-v1:0":
      { "inputTokens": 614, "outputTokens": 42237,
        "cacheReadInputTokens": 1520848, "cacheCreationInputTokens": 241256,
        "thinkingTokens": 19065, "costUSD": 1.9963614 },
    "global.anthropic.claude-haiku-4-5-20251001-v1:0":
      { "inputTokens": 2516, "outputTokens": 28, "costUSD": 0.002656 }
  },
  "totalCostUsd": 1.9990174,

  "tools": {
    "callCount": 72,
    "byName": { "Bash": 22, "mcp__pdf-tools__search_pdf": 14, "Read": 12,
                "mcp__pdf-tools__extract_text": 8, "Agent": 4,
                "mcp__pdf-tools__get_page_image": 4 },
    "resultChars": { "total": 2311124, "max": 654945, "p95": 434605 },
    "imageResultChars": 2054388,
    "meanInterCallGapMs": 4212
  },
  "mcp": {
    "exposed": ["pdf-tools", "artifact-storage"],
    "invoked": ["pdf-tools", "artifact-storage"],
    "toolsExposed": 10, "toolsInvoked": 5
  },
  "subagents": { "streamCount": 4, "byType": { "takeoff-engineer": 1, "…": 1 } },

  "contextHashes": {
    "prompt":      "3ab9…",
    "claudeMd":    "77d0…",
    "processFlow": "e1c8…",
    "rules":       "b1e4…",
    "agents":      { "takeoff-engineer": "5cc2…" },
    "skills":      { "extract-door-schedule": "9a70…" },
    "referenceData": { "margin_framework.json": "0d81…" }
  },
  "sourceHashes": {
    "uploads/raw/01_DTGO Prototype_ARCHITECTURAL.pdf": "c41b…"
  },
  "artifactHashes": {
    "extracted/door_schedule.json": "9f2c…",
    "priced/line_items.json": null
  },

  "cache": {
    "pdfRender":  { "hits": 0, "misses": 4 },
    "pdfText":    { "hits": 0, "misses": 22 },
    "sheetMap":   { "hits": 0, "misses": 1 },
    "catalogPage":{ "hits": 0, "misses": 0 },
    "matchDecision": { "hits": 0, "misses": 0 }
  },

  "outcome": {
    "status": "done",
    "errorCode": null,
    "retryReason": null,
    "rerunScope": null,
    "validationFailures": [],
    "reviewFlagCount": 0,
    "estimatorCorrections": null
  }
}
```

Indexes: `{jobType: 1, startedAt: -1}`, `{projectId: 1, startedAt: -1}`,
`{"contextHashes.prompt": 1}`, `{"outcome.errorCode": 1, startedAt: -1}`.
**No TTL** — this is cost and provenance evidence.

### Cache manifest document

```json
{
  "_id": "pdfRender:c41b…:12:200:none:pymupdf-1.24.9",
  "cache": "pdfRender",
  "key": { "sourceSha256": "c41b…", "page": 12, "dpi": 200,
           "region": null, "rendererVersion": "pymupdf-1.24.9" },
  "storagePath": ".cache/pdf-pages/1f8c….png",
  "bytes": 3151609,
  "pixelWidth": 7200, "pixelHeight": 4800,
  "createdAt": "2026-09-02T18:33:11Z",
  "lastReadAt": "2026-09-03T09:12:04Z",
  "readCount": 7,
  "invalidatedBy": null
}
```

### Derived views to build once `runMetrics` exists

| View | Query | Answers |
|---|---|---|
| Cost per job type | `$group` on `jobType`, avg/p95 `totalCostUsd` | Where the money goes |
| Cost split | `cacheCreate × 3.75e-6`, `cacheRead × 0.30e-6`, `output × 15e-6` | Whether T-01/T-06 landed |
| Cold-write count | avg `tokens.coldPrefixWrites` | The single best proxy for T-06 |
| Rerun cost | `sum(totalCostUsd) where attempt > 1` | The price of T-03 |
| Tool-schema waste | `mcp.toolsExposed - mcp.toolsInvoked` | Whether the scoping profiles are still right |
| Image share | `tools.imageResultChars / tools.resultChars.total` | Whether T-05 landed |
| Cache hit rate | per `cache.*` | Whether each cache is earning its keep |
| Prompt-change attribution | `$group` on `contextHashes.prompt`, avg cost | Which prompt edit moved the number |
| Estimator correction rate | join `runMetrics` to `lineItems` where `confirmedBy` set and the value differs | The quality guardrail: cost must not fall while corrections rise |

**The quality gate on every cost change:** median `totalCostUsd` per job type must fall
**and** `outcome.reviewFlagCount` plus the estimator correction rate must not rise. A
cheaper run that produces more manual work is a regression, not a saving.

---

## Assumptions and Unknowns

### Assumptions, stated so they can be checked

1. **Bedrock Sonnet 4.5 list pricing** — $3 / $15 / $3.75 / $0.30 per MTok for
   input / output / 5-min cache write / cache read. The per-run arithmetic reconciles to
   `costUSD` to seven decimal places under these rates, so they are effectively
   confirmed by the data (`"costBasis": "list"` in `modelUsage`).
2. **Subagents inherit the project instruction context.** The ten cold cache writes ≥8k
   tokens against four subagent streams are consistent with this, but the mechanism is
   Claude Code's, not the repository's. **Needs verification** — see U-1.
3. `@`-references inside `.claude/agents/*.md` (for example
   `pricing-engineer.md:102-105`) are assumed to inline into that subagent's context.
   `tests/pipeline/test_workflow_cost.py:62` already forbids agents inlining *rules*,
   which implies the mechanism works. **Needs verification** — U-2.
4. Image token cost is assumed to follow `(width × height) / 750` after client-side
   downscaling to a ≤1568 px long edge. The measured base64 sizes (401k–655k chars) are
   consistent with a resize having occurred. **Needs verification** — U-3.
5. The two recordings are representative. They are one extraction and one pricing pass
   on a 36-page set. A 744-page set is named in `prompts.py:328` but no recording of one
   exists here.

### Unknowns, and exactly what would resolve each

| # | Unknown | Why it matters | What resolves it |
|---|---|---|---|
| **U-1** | Does a subagent really re-load `CLAUDE.md` + rules, and is that the source of the ten cold writes? | Determines whether T-06's trimming is multiplied by 10 or by 1 — a 10× swing on the estimate | One instrumented run: log `cache_creation_input_tokens` against `parent_tool_use_id` per assistant message. B-06 produces this as a side effect |
| **U-2** | Do `@`-paths inside agent definitions inline? | ~15 KB of extra context on `pricing-engineer` alone | Same instrumented run: compare a subagent's first cache write against the same agent with the `@` lines replaced by plain paths |
| **U-3** | Exact image token cost after client resize | Sizes T-05 precisely (currently "≈6% of run A") | `runMetrics` with a run that uses images and one that does not, on the same bid |
| **U-4** | How often does artifact validation actually fail? | T-03 is the largest *worst-case* item and the least-known *expected* one | `outcome.validationFailures` over 30 days. `prompts.py:458-461` records at least one occurrence |
| **U-5** | Is the 1-hour cache TTL reachable from the CLI? | `ephemeral_1h_input_tokens: 0` in both runs. If reachable, it collapses the 43–45% cache-write line directly | Check the installed CLI version's flags/env. **Do not assume an env var name** — verify against the shipped binary before acting |
| **U-6** | Do the four page images improve extraction accuracy at all? | If not, T-05 becomes "remove the calls", not "crop them" | `scripts/score_extraction.py` on the same bid with and without vision |
| **U-7** | Per-phase model tiers under Bedrock | `provider.py:243-255` `_pin_model_aliases` collapses `sonnet`/`opus`/`haiku` onto one model on Bedrock/Cloudflare/Ollama | Test whether a distinct `ANTHROPIC_DEFAULT_HAIKU_MODEL` survives the pin, and whether the agent frontmatter `model:` is honoured |
| **U-8** | Real cost on a 744-page set | Every figure here is from a 36-page set | One recorded `run_full_pipeline` on a large bid, with B-06 shipped |
| **U-9** | Whether `pre_delete_guard.py` still admits a Bash-mediated write to protected paths | `docs/audit/R4-004_reference_data.md:101-117` raises it; commit `fa8d436` may have closed it | Read the guard and add an adversarial case to `tests/pipeline/test_hooks.py`. Out of scope here — flagged, not verified |
| **U-10** | Whether `.versions/` duplication is intended | 71 KB in `projects/refactored_test/.versions/` are byte-identical to the live artifacts | It appears to be by design (`artifact-storage/server.py:68-84` explicitly skips a duplicate blob when unchanged); confirm before pruning |

### Method note

Findings marked **measured** come from parsing `projects/refactored_test/.runs/*.log`
and from byte counts taken directly off the working tree. Findings marked **confirmed**
come from reading the cited code. Everything else is labelled **likely** or **needs
telemetry**, and the table above says what would settle it. No repository file was
modified in the course of this audit.
