# Fix plan — agentic configuration repair

Source of truth for what is done, pending or blocked. Findings and evidence live
in `system_map.md`; this file carries only the work.

Ordered low-risk and independent first; shared `CLAUDE.md` content last, since it
is read by every session.

---

## Task 0: Commit in-flight work before the audit touches anything
- **File(s):** `scripts/validate_project.py`, `apps/worker/prompts.py`, `src/cbc/services/sync.py`, `apps/worker/main.py`
- **Category:** cross-cutting
- **Problem:** Uncommitted fixes from earlier today (cost-source gate, false-approval rule, autopilot gating, payload-shape tolerance, `force` wiring) sit in the tree. Audit commits made on top would be unreadable as a diff.
- **Proposed fix:** Commit them as their own change. No edits. Leave the 10 deleted `projects/dutch_bros_macarthur_demo/` files unstaged — that deletion is the user's, not this audit's.
- **Risk:** low
- **Verification:** `python -m pytest tests -q` → 437 passed, 9 skipped; `git status --short` shows no modified source files.
- **Status:** done — 437 passed / 9 skipped, committed as `4ae2a9a`

## Task 1: Remove leftover directories from the PageIndex deletion
- **File(s):** `src/cbc/catalog/`, `src/cbc/documents/`, `mcp-servers/document-index/`, `mcp-servers/pricebook/`
- **Category:** cross-cutting
- **Problem:** All four are untracked (`git ls-files` → 0) and hold only `__pycache__`. They make `ls` contradict `CLAUDE.md` and `.mcp.json`.
- **Proposed fix:** Delete the four directories.
- **Risk:** low
- **Verification:** `python -m pytest tests -q` unchanged; `python mcp-servers/main.py --selftest` passes; the four paths no longer exist.
- **Status:** ready — in `scripts/apply_config_audit.py`, verified on a copy, awaiting the user's run
- **Notes:** `rm -rf` from inside a run is blocked by `pre_delete_guard.py` — the guard working as designed (`file-safety.md`: "rm -rf is blocked outside projects/"). Not bypassed. Moved into `scripts/apply_config_audit.py`, the same human-run mechanism the plan already requires for the `.claude/**` tasks. All four confirmed untracked with zero non-`.pyc` files before deferring.

## Task 2: `scan-product-catalog` skill contradicts the system it documents
- **File(s):** `.claude/skills/scan-product-catalog/SKILL.md` *(needs external script — `.claude` is guard-protected)*
- **Category:** skill
- **Problem:** Frontmatter promises *"returns list price with page-level traceability"*; the catalog tools deliberately return no prices (`mcp-servers/catalog/tools.py:3`). Lines 79 and 83 invoke `scripts/search_pricebook.py`, deleted by `apply_pageindex_prompts.py`.
- **Proposed fix:** Reword the description to say it returns the page to open; replace the `## Script` block with the `find_pages` → `extract_tables` sequence the body already teaches.
- **Risk:** low
- **Verification:** every `scripts/…` path in `.claude/skills/*/SKILL.md` resolves on disk; `grep -c search_pricebook` on the file → 0; frontmatter no longer contains "list price".
- **Status:** ready — in `scripts/apply_config_audit.py`, verified on a copy, awaiting the user's run
- **Notes:** Dry run confirms the frontmatter now says it returns the page, not a price, and the dead `## Script` block is replaced by the `find_pages` → `extract_tables` → `get_multiplier` sequence. One `search_pricebook` mention survives on purpose — a sentence saying it was deleted and why, so nobody goes looking for it.

## Task 3: Bootstrap gates the PageIndex build on a path that can never exist
- **File(s):** `scripts/bootstrap.py:51-69`, `scripts/fresh_reset.py:121,168`
- **Category:** cross-cutting
- **Problem:** `index_path` defaults to the deleted `.index/catalog.sqlite3`, so `if not index_path.exists()` is always true — `build_all()` walks every catalog on every worker start and prints a path it never writes.
- **Proposed fix:** Gate on whether the Mongo `pageIndex` collection is populated; correct the log message.
- **Risk:** low
- **Verification:** restart the worker — log names PageIndex, not `.sqlite3`, and reports skipping with 11 catalogs already indexed.
- **Status:** done — worker logs `[bootstrap] page index already built (11 catalogs)`; suite 437/9
- **Notes:** Scope grew once the file was read, and both additions are the same defect. `fresh_reset.py` dropped every collection **except** `pageIndex`, so a "fresh install" kept 11 indexed catalogs pointing at price books `reset_pricebooks()` had just deleted — `pageIndex` added to `COLLECTIONS`. And `reset_catalog_index()` stopped both containers to hunt for a `catalog_index` volume that no longer exists in `docker-compose.yml`, then probed the deleted SQLite file for a `products` table; the function, its call site and the now-dead `subprocess` import are gone.

## Task 4: No agent declares a `tools:` allowlist
- **File(s):** all 10 `.claude/agents/*.md` *(needs external script)*
- **Category:** agent
- **Problem:** 0 of 10 declare `tools:`, so in delegated mode every subagent inherits every tool. `toolsets.py` scopes per job type, not per agent.
- **Proposed fix:** Add a `tools:` line per agent, derived from the tools that agent's own body names, mirroring the `_READING` / `_PRICING` split at `toolsets.py:36,53`.
- **Risk:** medium — too narrow a list breaks a delegated run.
- **Verification:** every name in every `tools:` resolves to a server in `.mcp.json`; each agent's list is a superset of the `mcp__*` tools its body references.
- **Status:** ready — in `scripts/apply_config_audit.py`, verified on a copy, awaiting the user's run
- **Notes:** Dry run: all 10 frontmatters still parse as YAML, every `mcp__*` name resolves to a configured server, second run is a no-op. Written as explicit tool names, not `mcp__server__*` — wildcards work in `settings.json` permissions, but nothing in this repo demonstrates that agent frontmatter expands them, and a pattern that silently matched nothing would leave a subagent with no MCP tools at all. `quality-reviewer` gets no MCP tools because its own body line 14 says "You do not use external tools." Lists are deliberately generous where an agent's body named nothing: too wide only preserves today's behaviour, too narrow breaks a delegated run.

## Task 5: Solo runs never see the agent contracts — *root cause*
- **File(s):** `apps/worker/prompts.py` — `HOW_SOLO` **and** the `RUN_FULL_PIPELINE` schema block, in one change
- **Category:** cross-cutting
- **Problem:** `HOW_SOLO` never points at `.claude/agents/`, so the field contracts are invisible on the only path this provider uses. All 32 validation failures are fields specified there.
- **Proposed fix:** `HOW_SOLO` instructs reading `.claude/agents/<name>.md` immediately before each phase — one file at a time. In the same change, remove the duplicate schema block added to `RUN_FULL_PIPELINE` earlier today. Grouped: applying either half alone leaves the contract missing or duplicated.
- **Risk:** medium — changes core run behaviour.
- **Verification:** the rendered solo `run_full_pipeline` prompt names `.claude/agents/` and no longer contains "group and group_type are not optional"; then re-run the pipeline on CBC-260002 with `force` and confirm the 12 bbox/`page_size` and 20 `group`/`group_type` problems clear.
- **Status:** **verified** — forced run on CBC-260002 took validation problems from 32 to 6
- **Notes:** Blocked on the provider, not the change. Re-run when the limit clears: `docker compose exec worker python -c "import asyncio; from cbc.db import db; from cbc.services import jobs; ..."` enqueuing `run_full_pipeline` for CBC-260002 with `payload={"force": True}`, then confirm the 12 `bbox`/`page_size` and 20 `group`/`group_type` problems are gone. Static checks all pass: the rendered solo prompt reads the agent files, the duplicate block is gone, and `force` is honoured. Solo prompt now names `.claude/agents/<name>.md` and cites the concrete failure so the instruction reads as load-bearing rather than housekeeping. 1211 chars of duplicated schema removed from `RUN_FULL_PIPELINE` in the same change. Delegated path deliberately unchanged - "not files to read" is still correct there.

## Task 6: `CLAUDE.md` describes deleted subsystems
- **File(s):** `CLAUDE.md:17`, `CLAUDE.md:41-52`
- **Category:** CLAUDE.md
- **Problem:** Claims 6 MCP servers including deleted `document-index`; describes deleted `cbc/catalog/` (SQLite FTS5, `cbc.catalog.rebuild`) and `cbc/documents/`; never mentions `cbc/pageindex/`. Wrong context in every session.
- **Proposed fix:** Correct line 17 to five servers; replace 41–52 with a `cbc/pageindex/` description.
- **Risk:** high — shared content.
- **Verification:** `grep -cE "document-index|cbc\.catalog\.rebuild|SQLite FTS5" CLAUDE.md` → 0; `grep -c "cbc/pageindex" CLAUDE.md` → ≥1; stated server count equals `len(json.load(open('.mcp.json'))['mcpServers'])`.
- **Status:** done — 0 stale references; 5 == 5; every configured server named; every path resolves
- **Notes:** The one surviving "SQLite FTS5" mention is deliberate — a sentence explaining what PageIndex replaced and why, which is the context that stops someone rebuilding it.

## Task 7: `CLAUDE.md` duplicates content the rules already own
- **File(s):** `CLAUDE.md` — `## Scope`, `## Manual cut-off`
- **Category:** CLAUDE.md
- **Problem:** `## Scope` restates the auto-loaded `.claude/rules/scope-boundaries.md`; `## Manual cut-off` summarises the file it `@`-inlines on the next line. 27.5 KB reaches context every turn.
- **Proposed fix:** Reduce both to one-line pointers. Keep `## Non-negotiable guardrails` — 406 B, earns its place as an index.
- **Risk:** high — shared content; conservative, and no rule text is lost since both sources stay auto-loaded.
- **Verification:** the out-of-scope vendor list appears exactly once across auto-loaded files; `CLAUDE.md` shrinks with no rule losing its only statement.
- **Status:** done — Scranton / American Dryer / JL Industries now in `scope-boundaries.md` only; 9-ft doors / option permutation in `manual_cutoff.md` only; both owners still auto-loaded
- **Notes:** `## Non-negotiable guardrails` kept as planned. Net `CLAUDE.md` 8011 → 7620 B; the trim is larger than that figure suggests since Task 6 added the PageIndex description in the same file.

---

## Not doing

- `.mcp.json` — correct as-is: 5 servers, all referenced, all connected.
- `~/.claude.json` duplicate project entry — cosmetic; editing the global file is riskier than the symptom.
- Rewording agents or skills that are correct. This fixes defects, it does not redesign working prompts.

---

## Phase 3 — verification sweep

Re-ran the Phase 0 contradiction checks against the modified files:

| Original contradiction | Now |
|---|---|
| `CLAUDE.md` names deleted `document-index` | resolved |
| `CLAUDE.md` server count wrong (6 vs 5) | resolved |
| `CLAUDE.md` describes deleted `cbc/catalog` | resolved |
| `CLAUDE.md` describes deleted `cbc/documents` | resolved |
| `CLAUDE.md` omits `cbc/pageindex` | resolved |
| Scope list duplicated across two auto-loaded files | resolved |
| Manual cut-off prose duplicates the file it inlines | resolved |
| Bootstrap gates on the deleted SQLite path | resolved — the one surviving mention is a history comment, not code |
| `fresh_reset` does not drop `pageIndex` | resolved |
| Solo prompt hides the agent definitions | resolved |
| Duplicate schema block in `RUN_FULL_PIPELINE` | resolved |

`python mcp-servers/main.py --selftest` — all 5 servers start. Their reported tool
names match the allowlists in `apply_config_audit.py` exactly, which independently
validates Task 4 without needing the script to have run.

`python -m pytest tests -q` — 437 passed, 9 skipped.

**Not verified:** every subagent routing and every skill activation, and the
end-to-end pipeline run. All three need model calls, and the provider is
returning HTTP 429. Nothing in the audit's static checks depends on them.

---

## Task 5 verification — the forced run on CBC-260002

Job `6a968b7a`, `force: True`, provider `gemma4:31b-cloud` (solo).

| Check | Before | After |
|---|---|---|
| extraction | 12 — 6 × missing `bbox`, 6 × missing `page_size` | **6** — `bbox` only; `page_size` now populated |
| pricing | 20 — 10 × missing `group`, 10 × missing `group_type` | **0** — all 8 lines carry both |
| proposal | 0 | 0 |
| **total** | **32** | **6** |

The root-cause diagnosis holds. Every field that appeared was one specified in
an agent file the run could not previously see: `page_size`, `confidence` and
`flags` on openings (`takeoff-engineer.md:72`), `group` and `group_type` on every
priced line (`pricing-engineer.md:63`).

Honesty properties held through the change: 8 lines, **0 invented costs, 0 false
approvals**, everything `MANUAL` with a stated reason.

One artifact-shape bug surfaced and was fixed in the same pass: the run wrote a
complete schedule under `lines` rather than `openings`, and both the importer and
the stricter-still validator discarded it. See commit `b7985b8`.

### The remaining 6

All `bbox`. The requirement is fair and satisfiable — `pdfrows.rows_from_words`
returns 255 rows on PDF page 19 of this bid set, every one carrying a `bbox` —
and `takeoff-engineer.md:25` says the parse script returns it. The run took a
route that discarded the coordinates and flagged `bbox_missing` rather than
inventing them, which is the correct NFR-2 behaviour but still fails the gate.

Worth noting: `.claude/rules/auditability.md` lists `source_file`, `source_page`
and `extracted_at` as the required provenance — **not** `bbox`. The validator
enforces `bbox` as NFR-3 while the rule that defines NFR-3 does not require it.
Either the rule or the validator should move; that is a decision, not a bug fix.
