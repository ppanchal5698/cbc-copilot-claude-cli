# Ops-Hub Setup

The web application around the estimating pipeline: a Next.js UI, a FastAPI
service that owns MongoDB and every business rule, and a worker that runs Claude
Code on the estimator's behalf.

## Four processes

| Process | Command | Port |
|---|---|---|
| MongoDB | `docker compose up -d` | 27017 (mongo-express on 8081) |
| API | `python -m uvicorn api.main:app --reload --port 8000` | 8000 |
| Web | `npm --prefix web run dev` | 3000 |
| Worker | `python worker/main.py` | — |

`uvicorn` is not a PATH binary on this machine; use `python -m uvicorn`.

## First run

```bash
docker compose up -d
```

```bash
python -m pip install -e mcp-servers && python -m pip install fastapi uvicorn motor bcrypt python-multipart
```

```bash
python scripts/seed_db.py --reset --demo
```

```bash
npm --prefix web install
```

Then start the API, the web app and the worker in three terminals.

Sign in with `rgilbert@hamiltonparker.com` / `opshub`.

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
| Every page shows "Cannot reach the API" | API not running | `python -m uvicorn api.main:app --port 8000` |
| Jobs sit at `queued` | Worker not running, or Claude cannot authenticate | `python worker/main.py --preflight` |
| Viewer says the worker version does not match | pdf.js worker drifted | `node web/scripts/copy-pdf-worker.mjs` |
| `DOMMatrix is not defined` | pdf.js evaluated on the server | the viewer is loaded with `ssr: false`; keep it that way |
| Download PDF opens a print dialog | No WeasyPrint native libraries | expected on Windows; print to PDF, or install the GTK runtime |
