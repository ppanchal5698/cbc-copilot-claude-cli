# Ops-Hub Setup

The web application around the estimating pipeline: a Next.js UI, a FastAPI
service that owns MongoDB and every business rule, and a worker that runs Claude
Code on the estimator's behalf.

## Everything in containers

```bash
docker compose up -d --build
```

| Service | Port | Notes |
|---|---|---|
| `mongo` | 27017 | mongo-express on 8081 |
| `api` | 8001 | FastAPI; owns Mongo and every business rule |
| `web` | 3000 | Next.js standalone build |
| `worker` | — | claims jobs and runs `claude --print` |
| `litellm` | 4000 | optional, `--profile oss` |

`api` and `worker` are the **same image** - the API needs the Claude Code CLI too,
for the sign-in flow on the settings screen.

### Two things the image has to get right

**It runs as a non-root user.** Claude Code refuses
`--dangerously-skip-permissions` under root, so every job would fail at spawn.

**It declares `/app` a trusted workspace** (`docker/entrypoint.sh`). Claude Code
ignores a project's `permissions.allow` entries until the trust dialog has been
accepted, and an unattended container has nobody to accept it. Unset, every MCP
tool call is silently denied - which looks like an extraction that found nothing,
not like a permissions error.

### Running the processes directly instead

Still supported, and what `docs/headless_setup.md` assumes:

| Process | Command | Port |
|---|---|---|
| MongoDB | `docker compose up -d mongo` | 27017 |
| API | `python -m uvicorn api.main:app --reload --port 8001` | 8001 |
| Web | `npm --prefix web run dev` | 3000 |
| Worker | `python worker/main.py` | — |

`uvicorn` is not a PATH binary on this machine; use `python -m uvicorn`.

## First run

```bash
docker compose up -d --build
```

On first start, `docker/entrypoint.sh` runs [`scripts/bootstrap.py`](../scripts/bootstrap.py) when
`AUTO_BOOTSTRAP=1` (the default):

- Seeds users, price books, and sample catalog rows when the database is empty
- Builds the SQLite catalog index when `CATALOG_INDEX_PATH` does not exist yet

Deep document indexes (multiplier sheets, failed catalog layouts, bid PDFs) live
under `DOCUMENT_INDEX_ROOT` (default `.index/documents/`). Uploading a multiplier
sheet or a bid PDF enqueues an `index_document` job automatically. Manual rebuild:

```bash
python -m document_index.rebuild --client hager --type multiplier_sheet --file pricebooks/hager_multipliers.pdf --no-llm
```

Query via the `document-index` MCP server (`search_index` → `get_section_content`).
Status: `GET /api/document-index/{document_id}/status`.

Sign in with `estimator@cbc.com` or `admin@cbc.com` / `opshub`.

For a non-Docker local setup:

```bash
python -m pip install -e mcp-servers && python -m pip install -r requirements.txt
python scripts/bootstrap.py
npm --prefix web install
```

Then start the API, the web app, and the worker in three terminals.

To reset everything manually:

```bash
python scripts/seed_db.py --reset --demo
python -m catalog_index.rebuild
```

## Configuring Claude Code

**Settings → Claude Code.** Until this screen existed the worker inherited
whatever environment its shell had, so authentication was invisible from inside
the app and unfixable from outside it.

| Mode | Sets | Use it for |
|---|---|---|
| Claude subscription | `CLAUDE_CODE_OAUTH_TOKEN` | local development |
| Anthropic API key | `ANTHROPIC_API_KEY` (x-api-key) | per-token billing |
| Amazon Bedrock | `CLAUDE_CODE_USE_BEDROCK=1`, `AWS_REGION` | Fargate, via the task role |
| Gateway | `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` (Bearer) | LiteLLM, self-hosted |
| Ollama | `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN=ollama` + `ANTHROPIC_MODEL` | local dev with host Ollama |

These variables are **not interchangeable**. `ANTHROPIC_AUTH_TOKEN` goes in
`Authorization: Bearer`, `ANTHROPIC_API_KEY` in `x-api-key`. A credential in the
wrong one reaches the provider in a header it does not read and fails `401`.

**The environment wins over the screen.** On Fargate the credentials come from
Secrets Manager, and a field it sets renders read-only with a "set by
environment" badge rather than being silently ignored.

**Test connection** runs a real one-line pass against what is on screen, not
what is saved - so a wrong key is caught before it becomes the configuration
every job uses.

### Signing in through the browser

There is no browser in the container, so `claude setup-token` runs on a pty,
prints an authorization URL, and waits. Open the URL, approve, paste the code
back. The resulting one-year token is stored encrypted.

Local development only; it is refused when `APP_ENV=production`.

### Ollama (local dev)

Ollama on the host speaks the Anthropic Messages API directly — no LiteLLM
container is required. The api and worker reach it through
`host.docker.internal:11434` when running in Docker.

1. Install Ollama on the host ([ollama.com](https://ollama.com)).
2. Pull a model: `ollama pull qwen2.5-coder:32b` or `ollama pull glm-5:cloud`.
3. Start Ollama with enough context for CAD extractions:
   `OLLAMA_CONTEXT_LENGTH=65536 ollama serve` (or set the equivalent in your
   Ollama service).
4. **Settings → Claude Code → Ollama** — set the base URL, pick a model (Refresh
   models from Ollama), Test connection, Save.
5. Confirm the worker: `docker compose exec worker python worker/main.py --preflight`.

Local models use names like `qwen2.5-coder:32b`. Ollama Cloud models use a
`:cloud` suffix (e.g. `glm-5:cloud`, `kimi-k2.5:cloud`) and are pulled through
the same host daemon.

Set the background model to the same model or a smaller local one so session
title calls do not try to reach Anthropic Haiku. When Ollama mode is active, the
provider also maps the `sonnet`, `opus`, and `haiku` aliases — and
`CLAUDE_CODE_SUBAGENT_MODEL` — to your configured model so phase agents in
`.claude/agents/` do not try to call `claude-sonnet-5` on Anthropic.

**Agent-tool fidelity:** Ollama and other non-Anthropic models can run the
pipeline, but Agent delegation often fails (missing parameters, unrecognized
model aliases). Worker preflight and completed jobs surface warnings when this
is likely. For production pipeline jobs, Anthropic Sonnet is strongly
recommended; check job logs for `claude-code:unrecognized_model` or
`InputValidationError` on Agent calls.

Override the default host URL with `OLLAMA_BASE_URL` in `.env` when api/worker
run in Docker.

### Non-Claude models (LiteLLM gateway)

```bash
docker compose --profile oss up -d litellm
```

Claude Code speaks only Anthropic-format APIs. Ollama, NVIDIA NIM and OpenRouter
are OpenAI-format, so LiteLLM translates, exposing `/v1/messages` for
`ANTHROPIC_BASE_URL` to point at.

**Anthropic does not support Claude Code against non-Claude models.** Tool-use
fidelity degrades first, and this pipeline is almost entirely MCP tool calls - a
loosely formatted call yields an extraction that looks finished and is wrong.
Check anything these models produce against the drawing.

### Where credentials live

Encrypted with `APP_SECRET_KEY` (Fernet) in the `settings` collection, returned
to the browser masked, redacted from job logs, and recorded in the audit trail by
field name only - never by value. Changing `APP_SECRET_KEY` makes stored
credentials unreadable; they are reported as unconfigured, and re-entering them
is the fix.

## Watching a run

Every job runs the CLI on a pty and records it to
`projects/{slug}/.runs/{job_id}.log`. The header run pill opens that recording in
a real terminal (xterm.js), live while the job runs and replayable afterwards.

`--print` on a pty emits only the final answer - a whole extraction produced 14
bytes - so a recorded run uses `--output-format stream-json --verbose`, where the
CLI reports each tool call as it makes it. Each line in the terminal is one of
those events; `raw` shows the untouched stream. The interactive TUI would be
richer, but it stops on the login-method screen and cannot be driven unattended.

The terminal is read-only. Credentials are stripped as the recording is written,
including one split across two reads.

## What a run costs

The first real bid set spent a million-token budget without producing a
schedule. Four things were paying for that, and each is now bounded:

| Where it went | Before | Now |
|---|---|---|
| `CLAUDE.md` and its `@` includes, in context every turn | 72 KB (~18,000 tokens) | 13.7 KB (~3,400) |
| One `extract_tables(page_range="all")` | 1.54 M chars (~385,000 tokens) | bounded to 4 pages, rest named |
| Finding which sheets matter | 6 searches, ~2,300 tokens | one `find_sheets`, ~450 |
| Tools in context during a take-off | 6 MCP servers, 39 tools | 2 servers, 33 tools |

`@` inlines a file into every session and every turn, so a doc referenced that
way is paid for on every job forever. Only `cbc_process_flow.md` earns it. The
rest are plain paths, readable on demand. `tests/test_workflow_cost.py` fails if
that creeps back.

Each job also gets only the servers its phase uses (`cbc_core/toolsets.py`), passed
with `--strict-mcp-config`. An extraction sees pdf-tools and artifact-storage and
nothing else - which is a quality lever before it is a cost one, because the only
tools on offer are the right ones. `WebSearch` and `WebFetch` are removed
outright: a pass over a customer's drawings has no reason to reach the network.

`WORKER_MAX_TURNS` (default 60) bounds how far a pass can wander.

## MCP servers

They are declared in **`.mcp.json` at the repo root**. `.claude/settings.json`
has no `mcpServers` key and never had - a block there is silently ignored, which
is how the first real run ended up with no MCP tools at all and reimplemented PDF
extraction in Bash 52 times.

`enableAllProjectMcpServers: true` in `.claude/settings.json` is what lets an
unattended container use them: a project-scoped `.mcp.json` otherwise waits for
an approval nobody is there to give.

Check them with:

```bash
docker compose exec worker bash -lc "cd /app && claude mcp list"
```

## Reading a mis-encoded bid set

Some CAD exports embed fonts with no usable ToUnicode map, so `page.get_text()`
returns glyph codes: "DO NOT SCALE DRAWINGS" arrives as `'21276&$/(`.
`pdf-tools` detects a document-wide offset, repairs it, and reports
`encoding_repaired` and `encoding_shift` on every result - it is never applied
silently, because a transformed drawing value nobody can see was transformed is
what NFR-2 exists to prevent. A sound document is left untouched.

## How a bid flows

```
Estimator                          API                       Worker / Claude Code
─────────────────────────────────────────────────────────────────────────────────
create bid          ──▶ projects{}          scaffold projects/{slug}/
upload plan set     ──▶ documents{}         ──▶ jobs{extract_bid_set}
                                                        ──▶ claude --print
                                                            writes extracted/*.json
                        lineItems{}  ◀── worker syncs files into Mongo
review each line
  · real PDF + bbox highlight
  · confirm / edit / delete / add
Continue to Quote   ──▶ writes extracted/door_schedule.json back down
                        ──▶ jobs{match_and_price}
                                                        ──▶ claude --print
                                                            writes priced/*.json
                        quoteLines{} ◀── worker syncs
edit cost / margin  ──▶ calc-engine recomputes on every save
Continue to Proposal ─▶ writes priced/line_items.json back down
                        ──▶ jobs{build_proposal}
download the PDF
                        HALT — nothing is sent (NFR-1)
```

The estimator's decisions are written **down to disk** at each phase boundary, so
Claude's next pass reconciles against what the human confirmed rather than
overwriting it. Confirmed and hand-added lines survive a re-run.

## Alternates and addenda

Only the interim rule the workbook records is built. How a reconciliation
actually resolves is still open (Matrix 4.1 / FR-14 / Open Item 11), and the
screens say so rather than implying an answer.

- The base bid and each alternate are **distinct, comparable line groups** with
  independent totals. `alternateGroup: null` is the base bid; declared alternates
  are stored on the project so an empty one still appears in the switcher.
- Uploading a document of kind `addendum` **snapshots the whole current state**
  into a new version, then enqueues `ingest_addendum`. The prior version is kept
  entire, not diffed.
- That job writes `review/addendum_diff.json` and stops. It never merges the
  addendum into `door_schedule.json`, because the merge rule has not been agreed.

## Hand-off to sales

`Mark complete` records the estimator's sign-off, sets `handedOffTo`, puts the bid
in that person's queue, and writes the drafted body to
`review/quotation_email_draft.md`.

**Nothing is transmitted.** The response always carries `sent: false` and says so
in words, on both the routed and the no-initiator path. `pre_send_quote.py`, the
deny list and `test_no_auto_send.sh` are untouched (NFR-1).

## Why a worker rather than a direct spawn

Extraction on a 30-page CAD set is minutes of LLM work — longer than a web request
should hold open, and a dropped connection must not lose the job. The `jobs`
collection gives durability, one retry path, a visible run pill in the header, and
a single audited place where `claude --print` is invoked.

## Checking the Claude CLI

```bash
python worker/main.py --preflight
```

The CLI exits 0 even when authentication has failed, so the worker inspects the
output for auth markers rather than trusting the exit code. A failed preflight
names the problem instead of letting jobs fail silently.

```bash
python worker/main.py --once
```

Processes at most one job, which is the quickest way to see a real run end to end.

## Environment

`.env` (API and worker) and `web/.env.local` (Next.js). Copy `.env.example`.

| Variable | Used by | Notes |
|---|---|---|
| `MONGODB_URI` / `MONGODB_DB` | API, worker, catalog MCP | docker-compose default is pre-filled |
| `API_BASE_URL` | web | the Next.js server and proxy call this |
| `AUTH_SECRET` | web | NextAuth session signing |
| `CLAUDE_BIN` | worker | resolved with PATHEXT, so `claude.cmd` is found on Windows |
| `WORKER_JOB_TIMEOUT_SECONDS` | worker | default 1800 |
| `PRICEBOOK_DIR` | API, pricebook MCP | default `pricebooks/` |

The API runs on **8001**, not 8000. A dead process was holding 8000 on the build
machine and Windows no longer reported the owning PID, so the port moved rather
than being fought over.

## Where the data lives

**MongoDB** holds the structured record: projects, documents, line items, quote
lines, quotes, proposals, products, price books, jobs and the audit log.

**The filesystem** holds the PDFs, in the layout the existing skills already
expect — `projects/{slug}/uploads/raw/`. pdfplumber and PyMuPDF need real paths,
and keeping this layout means every agent, skill and test works unchanged. The
JSON under `extracted/` and `priced/` stays the audit artifact.

## The PDF viewer

The review screen renders the **real drawing** with pdf.js and draws a highlight
over the bounding box the value was read from. Checking Claude's output against a
re-rendering of Claude's output would verify nothing.

`bbox` is `[x0, y0, x1, y1]` in PDF points, measured against `pageSize`; the
viewer scales it by the rendered canvas width. The box is tightened to the cells
that actually carry the opening, because a CAD sheet puts unrelated notes on the
same horizontal band.

`web/scripts/copy-pdf-worker.mjs` runs on install and copies the pdf.js worker
that react-pdf actually resolves. The worker must match the API version exactly or
the viewer refuses to open a file.

## PDF download

The proposal downloads through WeasyPrint when its native libraries are present.
On Windows they usually are not, so the button falls back to the browser's own
print-to-PDF on the printable view. The API returns a 501 naming the problem
rather than a 500.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Every page shows "Cannot reach the API" | API not running | `python -m uvicorn api.main:app --port 8001` |
| Jobs sit at `queued` | Worker not running, or Claude cannot authenticate | `docker compose exec worker python worker/main.py --preflight` |
| `cannot be used with root/sudo privileges` | Container running as root | the image sets `USER cbc`; do not override it |
| `Ignoring N permissions.allow entries` | Workspace not trusted | `docker/entrypoint.sh` sets it; check it ran in the logs |
| `OAuth session expired` | No credential reached the container | configure a provider on the settings screen |
| Viewer says the worker version does not match | pdf.js worker drifted | `node web/scripts/copy-pdf-worker.mjs` |
| `DOMMatrix is not defined` | pdf.js evaluated on the server | the viewer is loaded with `ssr: false`; keep it that way |
| Download PDF opens a print dialog | No WeasyPrint native libraries | expected on Windows; print to PDF, or install the GTK runtime |
| A run reads the whole set and burns the context | MCP servers not registered | `claude mcp list` should show six connected |
| Extracted text is punctuation soup | Fonts carry no ToUnicode map | `pdf-tools` repairs it; check `encoding_repaired` on the result |
| The terminal says "no recording" | Job predates recording, or ran on a host with no pty | re-run it |
