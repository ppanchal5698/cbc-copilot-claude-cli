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

### On a Linux host, the mounted directories must belong to uid 1000

The containers run as the non-root user `cbc`, uid **1000**. `projects/` and
`pricebooks/` are bind-mounted, and a bind mount **replaces** the image's
directory — including the ownership the Dockerfile set — with whatever the host
has. If the host copies are owned by anyone else, the API cannot create a project
directory and `POST /api/projects` returns 500:

```
PermissionError: [Errno 13] Permission denied: '/app/projects/<slug>'
```

Once, before the first start:

```bash
sudo chown -R 1000:1000 projects pricebooks
```

**Docker Desktop on macOS and Windows does not enforce bind-mount ownership**, so
this never shows up there. It is not a CI quirk — it applies to any Linux
deployment, and CI has a step that does exactly the above.

On first start, `docker/entrypoint.sh` runs [`scripts/bootstrap.py`](../scripts/bootstrap.py) when
`AUTO_BOOTSTRAP=1` (the default):

- Seeds users, price books, and sample catalog rows when the database is empty
- Builds the PageIndex for any vendor sheet that does not have one yet

**PageIndex**, not a pre-extracted product table. One JSON document per catalog in
MongoDB's `pageIndex` collection describes *each page* - what it sells, which part
families are on it, whether it carries prices. A pricing pass asks it which page
to open and then reads the number off that page, so no stored value can be stale
about a price, because no price is stored.

Uploading a sheet enqueues `index_catalog`; deleting one enqueues `delete_catalog`
and the cascade drops its document. Rebuild the lot by hand - idempotent on the
file hash, so re-running it costs nothing for sheets that have not changed:

```bash
python -m cbc.pageindex.build --all
```

Query it through the `catalog` MCP server (`find_pages` → `get_page`), then read
the price with `pdf-tools`.

This replaced a SQLite FTS5 index that pre-extracted every product row. Vendor
catalogs are too irregular for that: 37.8% of the codes it produced contained no
letter at all, dates were recorded as part numbers, and one vendor's sheet yielded
nothing while reporting success.

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
python -m cbc.pageindex.build --all
```

## Configuring Claude Code

**Settings → Claude Code.** Until this screen existed the worker inherited
whatever environment its shell had, so authentication was invisible from inside
the app and unfixable from outside it.

| Mode | Sets | Use it for |
|---|---|---|
| Claude subscription | `CLAUDE_CODE_OAUTH_TOKEN` | local development |
| Anthropic API key | `ANTHROPIC_API_KEY` (x-api-key) | per-token billing |
| Amazon Bedrock | `CLAUDE_CODE_USE_BEDROCK=1`, `AWS_REGION`, `AWS_BEARER_TOKEN_BEDROCK` (optional), inference-profile `ANTHROPIC_MODEL` | Fargate via the task role, or a Bedrock API key locally |
| Cloudflare | AI Gateway URL + `ANTHROPIC_CUSTOM_HEADERS` (`cf-aig-authorization`), or a typed Workers `/v1/messages` URL | Anthropic, Bedrock, or Vertex through AI Gateway; OSS `@cf/` models on a Workers bridge |
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

### Amazon Bedrock

Claude Code talks to Bedrock when `CLAUDE_CODE_USE_BEDROCK=1` is set. Credentials
are either a Bedrock API key (`AWS_BEARER_TOKEN_BEDROCK`, typed on the settings
screen) or the Fargate task role — leave the key empty in production.

1. Enable the Claude models in the Amazon Bedrock console (once per account).
2. **Settings → Claude Code → Amazon Bedrock** — region, optional API key, model,
   optional background model. Test connection, then Save.
3. Confirm the worker: `docker compose exec worker python worker/main.py --preflight`.

Newer Claude models reject a foundation-model ID
(`anthropic.claude-sonnet-4-5-20250929-v1:0`). They need a cross-region inference
profile:

| AWS region | Prefix to use |
|---|---|
| `ap-south-1`, `ap-south-2` (India) | `global.` — Global CRIS, not `apac.` |
| `us-*` | `us.` |
| `eu-*` | `eu.` |
| other `ap-*` | `apac.` |

A bare `anthropic.…` ID typed on the screen is rewritten at spawn time to that
prefix. The stored value is left as typed, so a re-save is not required. The
same rewrite pins `ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_OPUS_MODEL`,
`ANTHROPIC_DEFAULT_HAIKU_MODEL`, and `CLAUDE_CODE_SUBAGENT_MODEL` so phase agents
that declare `model: sonnet` do not resolve `opus` to Opus 5 from Claude Code's
Bedrock catalog.

`ANTHROPIC_BEDROCK_REGION_PREFIX` is set from the region (overridable from the
environment) so unpinned aliases follow the same geography.

On Fargate the task role supplies credentials and any of these variables in
Secrets Manager lock the matching field on the screen.

**Settings → Save** also writes the Bedrock API key (and the other provider
fields for the selected mode) into the repo `.env` as `AWS_BEARER_TOKEN_BEDROCK`.
The file is gitignored and created with mode `600`. The worker rereads it on
every job, so a new key is live without restarting the container. Process
environment still wins — that is how Fargate stays authoritative.

Copy `.env.example` to `.env` **before** `docker compose up`. If the file is
missing, Docker mounts a directory at `/app/.env` and Save cannot write the key.

### Cloudflare (AI Gateway)

Claude Code does not speak Workers AI natively. The documented path is
[AI Gateway](https://developers.cloudflare.com/ai-gateway/integrations/coding-agents/claude-code/),
which exposes Anthropic, Amazon Bedrock, and Google Vertex as Anthropic-compatible
endpoints. A fourth Settings route accepts a custom URL that already speaks
`/v1/messages` (a Workers bridge you deployed elsewhere — this repo does not
ship one).

1. Create an AI Gateway in the Cloudflare dashboard and a token with **Run**
   permission.
2. **Settings → Claude Code → Cloudflare** — account ID, gateway ID, token,
   route, model. Test connection, then Save.
3. Confirm the worker: `docker compose exec worker python worker/main.py --preflight`.

| Route | What Claude Code gets |
|---|---|
| Anthropic | `ANTHROPIC_BASE_URL=https://gateway.ai.cloudflare.com/v1/<account>/<gateway>/anthropic`, `ANTHROPIC_CUSTOM_HEADERS=cf-aig-authorization: Bearer <token>` |
| Bedrock via Gateway | `CLAUDE_CODE_USE_BEDROCK=1`, `CLAUDE_CODE_SKIP_BEDROCK_AUTH=1`, `ANTHROPIC_BEDROCK_BASE_URL=…/aws-bedrock/bedrock-runtime/<region>/`. No AWS keys. |
| Vertex via Gateway | `CLAUDE_CODE_USE_VERTEX=1`, `CLAUDE_CODE_SKIP_VERTEX_AUTH=1`, `ANTHROPIC_VERTEX_BASE_URL=…/google-vertex-ai/v1`, plus project ID and `CLOUD_ML_REGION`. |
| Workers AI bridge | The typed `ANTHROPIC_BASE_URL`. Sonnet/opus/haiku aliases pin to the configured model. Agent-tool delegation is off — OSS `@cf/` models do not reliably call it. |

**Unified Billing:** leave the Anthropic API key empty. The gateway token is
used as `ANTHROPIC_API_KEY` (Claude Code requires one) and as
`cf-aig-authorization`. **BYOK:** paste a real Anthropic key as well; the
gateway forwards it and still authenticates with the token header.

Model IDs: Anthropic/Bedrock/Vertex routes take Claude IDs
(`claude-sonnet-4-5`, or a Bedrock inference-profile ID). The Workers route
takes whatever the bridge serves (`@cf/…`).

Save writes the constructed Claude variables — including
`ANTHROPIC_CUSTOM_HEADERS` — into `.env`, not only the raw account/gateway
pieces. Switching provider clears them.

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
| `WORKER_JOB_TIMEOUT_SECONDS` | worker | default 3600 |
| `PRICEBOOK_DIR` | API, pricebook MCP | default `pricebooks/` |
| `AWS_BEARER_TOKEN_BEDROCK` | worker, Test connection | written by Settings into `.env`; not injected by Compose |

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
