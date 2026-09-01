# Agentic configuration — system map

Audit date: 2026-09-01. Snapshot of `CLAUDE.md`, `.claude/`, `.mcp.json`,
`~/.claude.json` and the settings files, taken before any repair.

Placed under `docs/` rather than `.claude/_audit/` because `.claude` is a
`PROTECTED_DIR` in `.claude/hooks/pre_delete_guard.py:19` — no write into it
succeeds from inside a run.

---

## 1. Files read

| Path | Role | Size | Summary |
|---|---|---|---|
| `CLAUDE.md` | project instructions, auto-loaded every turn | 8.0 KB | System purpose, architecture layers, guardrail index, scope, vendor priority |
| `~/.claude/CLAUDE.md` | global instructions | 231 B | `graphify` skill pointer only — no conflict with the project |
| `CLAUDE.local.md` | — | absent | — |
| `.mcp.json` | project MCP scope | 686 B | 5 stdio servers, all `python ./mcp-servers/<name>/server.py` |
| `~/.claude.json` | global MCP + project registry | 64 KB | **Zero** global `mcpServers`; two entries for this repo (see §6) |
| `.claude/settings.json` | hooks + permissions | — | 2 PreToolUse matchers, 2 PostToolUse matchers, allow/deny lists |
| `.claude/settings.local.json` | local overrides | 231 B | Empty P21 placeholders; gitignored at `.gitignore:11`, untracked |
| `.claude/agents/*.md` | 10 subagents | 33.6 KB | One per pipeline phase |
| `.claude/skills/*/SKILL.md` | 9 skills | — | One per reusable task workflow |
| `.claude/rules/*.md` | 8 rules | 11.6 KB | Auto-loaded as project instructions |
| `.claude/hooks/*.py` | 5 hooks | — | All 5 referenced by `settings.json` exist |
| `.claude/memory/*.md` | 13 reference files | — | Domain data; one is `@`-inlined by `CLAUDE.md` |
| `.claude/commands/` | — | absent | — |
| `~/.claude/agents/` | — | absent | No global agents apply |

**Format check:** all JSON parses; all 19 YAML frontmatter blocks valid; every
required field (`name`, `description`) present on every agent and skill.

---

## 2. Dependency graph

### Skills → assets

| Skill | References | Resolves |
|---|---|---|
| extract-door-schedule | `scripts/parse_schedule.py`, `references/schedule_anatomy.md` | yes |
| generate-quotation | `scripts/render_quote.py`, `templates/quotation.html` | yes — template is at **repo root**, reached via `ROOT = parents[4]` |
| apply-margin | `references/margin_bands.md` | yes |
| frp-takeoff | `references/frp_constants.md` | yes |
| match-hardware-sets | `references/hw_set_library.md` | yes |
| price-line-item | `references/cost_paths.md` | yes |
| validate-extraction | `scripts/validate_project.py` | yes — repo root, `--check-extraction` flag exists |
| reuse-prior-quote | — | n/a |
| **scan-product-catalog** | `scripts/search_pricebook.py` | **NO — deleted** (SKILL.md:79, 83) |

### Agents → tools

**No agent declares a `tools:` allowlist** — 0 of 10. Each carries only `name`,
`description`, `model: sonnet`. In delegated mode every subagent therefore
inherits the full toolset. `src/cbc/core/toolsets.py` scopes MCP servers per
**job type** (`_READING` at :36, `_PRICING` at :53), not per agent, so nothing
else narrows this.

### MCP: configured vs referenced vs connected

| Server | `.mcp.json` | agents | skills | `CLAUDE.md` | connected |
|---|---|---|---|---|---|
| pdf-tools | yes | 2 | 3 | 1 | yes |
| calc-engine | yes | 2 | 2 | 1 | yes |
| artifact-storage | yes | 1 | 1 | 0 | yes |
| p21-connector | yes | 1 | 1 | 0 | yes |
| catalog | yes | 2 | 3 | 0 | yes |
| `pricebook` | no | 0 | 0 | 0 | disconnected — server deleted |
| `document-index` | no | 0 | 0 | 0 | disconnected — server deleted |

- **Orphaned configs (defined, never connected):** none.
- **Orphaned usage (assumed, not provided):** none. All 9 distinct `mcp__*`
  references inside `.claude/` resolve to a live tool.
- **Scope conflict:** none. `~/.claude.json` defines no servers, so `.mcp.json`
  is uncontested. `enableAllProjectMcpServers: true`.

### `CLAUDE.md` ↔ rules/skills overlap

| `CLAUDE.md` section | Size | Also owned by | Both auto-loaded? |
|---|---|---|---|
| `## Scope` | 514 B | `.claude/rules/scope-boundaries.md` | **yes — duplicated** |
| `## Manual cut-off` | 320 B | `@.claude/memory/manual_cutoff.md`, inlined on the next line | **yes — duplicated** |
| `## Non-negotiable guardrails` | 406 B | the 8 rule files | yes, but serves as an index — kept |
| `## The Ops-Hub application` | 3.5 KB | — | unique, but **stale** (§4) |

Per-turn context: `CLAUDE.md` 8.0 KB + `@docs/cbc_process_flow.md` 6.4 KB +
`@.claude/memory/manual_cutoff.md` 1.5 KB + `.claude/rules/*` 11.6 KB = **27.5 KB**.

---

## 3. The delegation gap (root cause of the CBC-260002 failures)

The configured provider is `ollama` / `gemma4:31b-cloud`, which cannot call the
Agent tool. Every run logs `provider cannot delegate; using the solo prompt`.

- `HOW_DELEGATED` (`apps/worker/prompts.py`) tells a delegating run: *"they are
  registered subagent types, not files to read. Reading their definitions with
  `cat` puts their whole text in this context and gains nothing."* Correct there.
- `SOLO_RULE` / `HOW_SOLO` never supply a substitute, and only `INGEST_ADDENDUM`
  (:223) and `INGEST_PRICEBOOK` (:319) name a `.claude/agents/` path at all.

So on the only path this deployment runs, **all 10 agent definitions are loaded
by nothing** — including the field contracts the artifact validator enforces:

| File | Line | Requires |
|---|---|---|
| `takeoff-engineer.md` | 72–73 | `bbox`, `page_size`, `confidence`, `flags` — *"the sheet viewer cannot highlight a row without bbox and page_size"* |
| `pricing-engineer.md` | 63 | `line_id`, `group`, `group_type`, `part_number` **or** `description`, `cost` |

The last run failed with exactly 12 × missing `bbox`/`page_size` and 20 ×
missing `group`/`group_type`.

Skills are unaffected — they load via the Skill tool, which the audit trail shows
firing in solo runs.

---

## 4. `CLAUDE.md` accuracy

| Line | Claim | Reality |
|---|---|---|
| 17 | "6 tool providers (pdf, catalog, calc, storage, P21, document-index)" | `.mcp.json` has **5**; document-index deleted |
| 41–49 | `cbc/catalog/` — SQLite FTS5 index, `python -m cbc.catalog.rebuild`, named volume | package deleted; only `__pycache__` remains |
| 50–52 | `cbc/documents/` — LLM deep indexing, versioning, diffing | package deleted |
| — | *(absent)* | `cbc/pageindex/` — now the core of pricing — unmentioned |

---

## 5. Enforcement reality

`src/cbc/core/claude_cli.py:103,123` spawns every run with
`--dangerously-skip-permissions`. The `permissions.allow` / `deny` lists in
`settings.json` — including `Bash(rm -rf *)`, `Bash(git push *)` and
`mcp__p21-connector__write_*` — are therefore **bypassed on every pipeline run**
and protect interactive sessions only.

What actually enforces the guardrails during a run:

| Hook | Event | Enforces |
|---|---|---|
| `pre_send_quote.py` | PreToolUse | NFR-1 — no send |
| `pre_delete_guard.py` | PreToolUse | file-safety — writes/deletes outside `projects/`, incl. `.claude`, `pricebooks`, `reference-library` |
| `post_extraction_validate.py` | PostToolUse | extraction shape |
| `post_quote_format.py` | PostToolUse | quote shape |
| `log_audit_trail.py` | PostToolUse `*` | NFR-3 — verified firing, 92 entries in the last run |

---

## 6. Leftovers and cosmetics

- Untracked, `__pycache__`-only directories left by the PageIndex deletion:
  `src/cbc/catalog/`, `src/cbc/documents/`, `mcp-servers/document-index/`,
  `mcp-servers/pricebook/`.
- `scripts/bootstrap.py:51` gates the PageIndex build on `.index/catalog.sqlite3`
  — the deleted SQLite path, which can never exist — so `build_all()` runs on
  every worker start and logs a path it never writes.
  `scripts/fresh_reset.py:121,168` carries the same dead path.
- `~/.claude.json` holds two entries for this repo, one backslash-pathed and one
  forward-slash-pathed; the latter has `hasTrustDialogAccepted: false`. Cosmetic.
