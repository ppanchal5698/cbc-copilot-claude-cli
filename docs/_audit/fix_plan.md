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
- **Status:** pending

## Task 2: `scan-product-catalog` skill contradicts the system it documents
- **File(s):** `.claude/skills/scan-product-catalog/SKILL.md` *(needs external script — `.claude` is guard-protected)*
- **Category:** skill
- **Problem:** Frontmatter promises *"returns list price with page-level traceability"*; the catalog tools deliberately return no prices (`mcp-servers/catalog/tools.py:3`). Lines 79 and 83 invoke `scripts/search_pricebook.py`, deleted by `apply_pageindex_prompts.py`.
- **Proposed fix:** Reword the description to say it returns the page to open; replace the `## Script` block with the `find_pages` → `extract_tables` sequence the body already teaches.
- **Risk:** low
- **Verification:** every `scripts/…` path in `.claude/skills/*/SKILL.md` resolves on disk; `grep -c search_pricebook` on the file → 0; frontmatter no longer contains "list price".
- **Status:** pending

## Task 3: Bootstrap gates the PageIndex build on a path that can never exist
- **File(s):** `scripts/bootstrap.py:51-69`, `scripts/fresh_reset.py:121,168`
- **Category:** cross-cutting
- **Problem:** `index_path` defaults to the deleted `.index/catalog.sqlite3`, so `if not index_path.exists()` is always true — `build_all()` walks every catalog on every worker start and prints a path it never writes.
- **Proposed fix:** Gate on whether the Mongo `pageIndex` collection is populated; correct the log message.
- **Risk:** low
- **Verification:** restart the worker — log names PageIndex, not `.sqlite3`, and reports skipping with 11 catalogs already indexed.
- **Status:** pending

## Task 4: No agent declares a `tools:` allowlist
- **File(s):** all 10 `.claude/agents/*.md` *(needs external script)*
- **Category:** agent
- **Problem:** 0 of 10 declare `tools:`, so in delegated mode every subagent inherits every tool. `toolsets.py` scopes per job type, not per agent.
- **Proposed fix:** Add a `tools:` line per agent, derived from the tools that agent's own body names, mirroring the `_READING` / `_PRICING` split at `toolsets.py:36,53`.
- **Risk:** medium — too narrow a list breaks a delegated run.
- **Verification:** every name in every `tools:` resolves to a server in `.mcp.json`; each agent's list is a superset of the `mcp__*` tools its body references.
- **Status:** pending

## Task 5: Solo runs never see the agent contracts — *root cause*
- **File(s):** `apps/worker/prompts.py` — `HOW_SOLO` **and** the `RUN_FULL_PIPELINE` schema block, in one change
- **Category:** cross-cutting
- **Problem:** `HOW_SOLO` never points at `.claude/agents/`, so the field contracts are invisible on the only path this provider uses. All 32 validation failures are fields specified there.
- **Proposed fix:** `HOW_SOLO` instructs reading `.claude/agents/<name>.md` immediately before each phase — one file at a time. In the same change, remove the duplicate schema block added to `RUN_FULL_PIPELINE` earlier today. Grouped: applying either half alone leaves the contract missing or duplicated.
- **Risk:** medium — changes core run behaviour.
- **Verification:** the rendered solo `run_full_pipeline` prompt names `.claude/agents/` and no longer contains "group and group_type are not optional"; then re-run the pipeline on CBC-260002 with `force` and confirm the 12 bbox/`page_size` and 20 `group`/`group_type` problems clear.
- **Status:** pending

## Task 6: `CLAUDE.md` describes deleted subsystems
- **File(s):** `CLAUDE.md:17`, `CLAUDE.md:41-52`
- **Category:** CLAUDE.md
- **Problem:** Claims 6 MCP servers including deleted `document-index`; describes deleted `cbc/catalog/` (SQLite FTS5, `cbc.catalog.rebuild`) and `cbc/documents/`; never mentions `cbc/pageindex/`. Wrong context in every session.
- **Proposed fix:** Correct line 17 to five servers; replace 41–52 with a `cbc/pageindex/` description.
- **Risk:** high — shared content.
- **Verification:** `grep -cE "document-index|cbc\.catalog\.rebuild|SQLite FTS5" CLAUDE.md` → 0; `grep -c "cbc/pageindex" CLAUDE.md` → ≥1; stated server count equals `len(json.load(open('.mcp.json'))['mcpServers'])`.
- **Status:** pending

## Task 7: `CLAUDE.md` duplicates content the rules already own
- **File(s):** `CLAUDE.md` — `## Scope`, `## Manual cut-off`
- **Category:** CLAUDE.md
- **Problem:** `## Scope` restates the auto-loaded `.claude/rules/scope-boundaries.md`; `## Manual cut-off` summarises the file it `@`-inlines on the next line. 27.5 KB reaches context every turn.
- **Proposed fix:** Reduce both to one-line pointers. Keep `## Non-negotiable guardrails` — 406 B, earns its place as an index.
- **Risk:** high — shared content; conservative, and no rule text is lost since both sources stay auto-loaded.
- **Verification:** the out-of-scope vendor list appears exactly once across auto-loaded files; `CLAUDE.md` shrinks with no rule losing its only statement.
- **Status:** pending

---

## Not doing

- `.mcp.json` — correct as-is: 5 servers, all referenced, all connected.
- `~/.claude.json` duplicate project entry — cosmetic; editing the global file is riskier than the symptom.
- Rewording agents or skills that are correct. This fixes defects, it does not redesign working prompts.
