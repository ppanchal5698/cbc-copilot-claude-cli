# Guardrails

Every non-functional requirement mapped to the thing that actually enforces it.
A rule with no enforcement is a wish.

## NFR-1 - Human-in-the-loop

**No estimate or quotation is sent without explicit estimator approval.**

| Mechanism | Type | What it does |
|---|---|---|
| `.claude/hooks/pre_send_quote.py` | PreToolUse hook | Exit 2 on `sendmail`, `mailx`, `mutt`, `msmtp`, `postfix`, `swaks`, `smtp*` (incl. `smtplib`), `sendgrid`, `mailgun`, `postmark`, `curl ... mail`, and any tool name containing send/email/mail |
| `.claude/settings.json` deny list | Permission | `Bash(sendmail *)`, `Bash(mailx *)`, `Bash(curl *mail*)` |
| `.claude/rules/human-in-the-loop.md` | Rule | Loaded every session |
| `.claude/agents/delivery-agent.md` | Agent | Halts with "Draft ready for estimator review" |
| `templates/review_summary.html` | Interface | Estimator accepts/edits/deletes/adds before approval |

Verify: `bash tests/test_guardrails/test_no_auto_send.sh` - 13 checks, all must pass.

## NFR-2 - Accuracy and trust

**Confidence visible from day one; nothing low-confidence is silently guessed.**

| Mechanism | Type | What it does |
|---|---|---|
| `.claude/rules/accuracy-trust.md` | Rule | Confidence bands, flag threshold 0.75 |
| Confidence score on every match | Data contract | `product-matcher`, validated by `validate_project.py` |
| `.claude/hooks/post_extraction_validate.py` | PostToolUse hook | Warns on missing required fields after every write to `extracted/` |
| `.claude/skills/validate-extraction/` | Skill | Required-field checklist and the anti-inference rule |
| `.claude/memory/manual_cutoff.md` | Memory | Where to stop rather than guess |

The anti-inference rule is explicit about the failure mode that matters: copying a
rating from a neighbouring row, defaulting handing to LH, assuming US26D, picking
the nearest stock item, extrapolating a price. Each produces a quote that looks
finished and is wrong.

## NFR-3 - Auditability

**Every line traces to a source page and a price-sheet version.**

| Mechanism | Type | What it does |
|---|---|---|
| `source_page` on every extraction result | Data contract | Enforced by `pdf-tools`; a hard error in `validate_project.py` |
| Cost provenance on every priced line | Data contract | `cost_source`, `cost_source_detail`, `multiplier_tier`, `multiplier_effective_date`, `price_book_version`, `priced_at` |
| `.claude/hooks/log_audit_trail.py` | PostToolUse hook, matcher `*` | Appends JSONL for every tool call; always exit 0 |
| `scripts/export_audit_report.py` | Script | Renders the trail plus cost provenance as HTML |
| `pricebooks/index.json` | Data | Effective date per price book |
| `mcp-servers/artifact-storage` | MCP | SHA-256 versioned copies of every artifact written |

## NFR-5 - P21 read-only

**No write-back, initially or otherwise.**

| Mechanism | Type | What it does |
|---|---|---|
| `mcp-servers/p21-connector/tools.py` | Design | Exposes only `lookup_last_po`, `check_freshness`, `search_item` |
| Import-time assertion in `server.py` | Code | Fails to start if any tool name contains write/update/insert/post/create/delete/set_ |
| `.claude/rules/p21-read-only.md` | Rule | Also forbids trusting the supplier-list/cost fields |

When P21 is unreachable - which is every time today - the connector returns a
structured "manual entry required" response. It never returns a guessed price.

## NFR-8 - Margin governance (DEFERRED)

**Below-band margins are flagged. Nothing is routed for approval.**

| Mechanism | Type | What it does |
|---|---|---|
| `mcp__calc-engine__validate_margin` | MCP tool | pass/fail against the band floor |
| `apply_margin` warning | MCP tool | Warns when a margin is overridden with no recorded reason |
| `.claude/rules/margin-governance.md` | Rule | States plainly that routing is deferred |

There is no margin deviation today, so approval routing would be ceremony. It
becomes relevant with more estimators.

## NFR-10 - Data stewardship (OPEN)

**No owner and no refresh cadence have been assigned.** This is a real gap, not a
solved problem.

| Interim mitigation | What it does |
|---|---|
| `pricebooks/index.json` | Records an effective date per book |
| `scripts/refresh_pricebooks.sh` | Reports age, warns past 180 days |
| `validate_project.py --all` | Surfaces stale books in pre-flight |
| Manual-entry refresh prompt | "price may be out of date - refresh" on every distributor line |
| P21 freshness rule | Independent age check on last-PO costs |

Today 11 of 26 price books are past 180 days and 7 carry no effective date at all.
That is visible on every run, which is the most this layer can do until an owner
is named.

## File safety

**Never delete outside `projects/`. Never write to reference data during a run.**

| Mechanism | Type | What it does |
|---|---|---|
| `.claude/hooks/pre_delete_guard.py` | PreToolUse hook | Exit 2 on `rm -rf` outside `projects/`, any `rm` touching `pricebooks/` or `reference-library/`, and `git push` |
| `.claude/settings.json` deny list | Permission | `Bash(rm -rf *)`, `Bash(git push *)` |
| `artifact-storage` path guard | MCP | Refuses any path that escapes `projects/{project}/` |
| `.claude/rules/file-safety.md` | Rule | Raw uploads are immutable |

Verify: `bash tests/test_guardrails/test_file_safety.sh` - 10 checks, all must pass.

## Scope boundaries

`.claude/rules/scope-boundaries.md` plus `spec-scope-analyst`. Out-of-scope items
found in a bid set are **recorded with their source page and never priced**, so
the estimator can tell the GC what CBC is not covering.

## Why the hooks are Python

`jq` is not installed on the target machine. A jq-based hook exits 127 when jq is
missing, which does not equal 2, which means the call is **not blocked**. A
guardrail that silently stops guarding is worse than no guardrail, so the hooks
parse their JSON with the standard library.

## Running the pipeline unattended

`workflows/run_full_pipeline.sh` uses `--dangerously-skip-permissions` because an
unattended run cannot answer prompts. The safety comes from the hooks, which run
regardless of permission mode. Verify both guardrail suites before trusting an
unattended run.

## The accepted security posture

This is the model in full, so an operator can see what guards what — and what is
not guarded at all.

### Why permissions are skipped, and what replaces them

`--dangerously-skip-permissions` is not optional for a headless run: the
permission prompt has nobody to answer it, and `cbc/core/claude_cli.py` spawns
every pass with the flag for that reason. The permission system is therefore
**not** part of the defence. These are:

| Control | Where | What it stops |
|---|---|---|
| `pre_send_quote.py` | PreToolUse, exit 2 | Any send — mail binaries, SMTP, curl to a mail API, any tool named send/email/mail (NFR-1) |
| `pre_delete_guard.py` | PreToolUse, exit 2 | `rm -rf` outside `projects/`, and pushing to a remote |
| `post_extraction_validate.py` | PostToolUse | Extraction output that fails its schema |
| `post_quote_format.py` | PostToolUse | Quote output that fails its schema |
| `log_audit_trail.py` | PostToolUse | Nothing — it records every tool call to `audit_trail.jsonl` |
| `cbc/core/toolsets.py` | `--strict-mcp-config` | Tools outside the phase's profile; WebSearch, WebFetch and NotebookEdit everywhere |
| `p21-connector` | Asserts at import | Any write to P21 (NFR-5) — the server exposes no write tool |
| `catalog` | Read-only Mongo credential | Any write to the catalog; `MONGODB_URI` is withheld from the subprocess entirely |

Hooks fire regardless of permission mode. That is the whole reason the posture
holds, and it is why a hook that fails open is a security bug rather than a bug —
see "Why the hooks are Python" above.

Note that these hooks match on command text, so they occasionally block a command
that merely *mentions* a forbidden operation. That is the correct direction to
fail in.

### The API's trust boundary

`INTERNAL_API_TOKEN` authenticates **the Next.js server, not the person**. The
signed-in human arrives as `X-Actor`, which the API trusts because only a caller
holding the token can set it. Two consequences to plan around:

- Anything that can reach the API port **and** holds the token can name itself any
  actor. The role is read from the database rather than the header, so privilege
  cannot be forged — but identity can.
- The API therefore binds to **loopback only** (`API_BIND`, default `127.0.0.1`),
  as MongoDB already did. Publishing it on `0.0.0.0` puts that boundary on every
  interface of the host. Do not, unless something genuinely off-box needs it and
  there is a network control in front of it.

An empty `INTERNAL_API_TOKEN` is refused: it used to skip the comparison entirely
and authenticate every caller, in any environment, silently. `APP_ENV=production`
or `staging` additionally refuses the committed development values for the token,
`APP_SECRET_KEY` and the Mongo password (`cbc/config.py`).

### What is not guarded

- **Prompt injection from bid sets and vendor sheets.** These are third-party PDFs
  and nothing vets their text. The preamble tells a run to treat PDF content as
  data and to record, not obey, anything addressing it — an instruction, not a
  control. A pass cannot send (a hook enforces NFR-1) and cannot write outside its
  project, so the realistic damage is a wrong quote, which is what the estimator
  review exists to catch.
- **The provider credential.** Whoever can run the worker can read what the worker
  is configured with. `provider.WITHHELD` keeps the writable Mongo URI out of the
  subprocess; it does not sandbox the pass.
- **Rate limiting beyond sign-in.** `/api/auth/verify` is budgeted per address in
  MongoDB, across replicas. Nothing else is rate-limited, on the assumption the
  API is not publicly reachable — the same assumption the loopback bind enforces.
