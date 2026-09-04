# Ops-Hub scaling guide

This document captures the current throughput ceiling and the changes needed
before multiple estimators can run the pipeline concurrently in production.

## Current architecture limits

| Layer | Constraint | Symptom |
|-------|------------|---------|
| Worker | `WORKER_CONCURRENCY` (default 1); scale worker service only with shared `./projects` | One Claude pass used to block all other jobs |

| Filesystem | `projects/` bind mount shared only between api + worker on one host | Second worker on another node cannot read PDFs |
| MongoDB | Single instance, no sharding | Dashboard/list queries scale with bid count |
| Job queue | Global FIFO (oldest queued job first) | Price book ingest waits behind long extractions |

## Worker concurrency

**Same host, typed concurrency (implemented)**

- `WORKER_CONCURRENCY` (default `1`) runs that many `process()` tasks in one worker process. `claim()` stays atomic; exclusive pipeline jobs per bid stay on the partial unique index.
- The worker service has no `container_name`, so `docker compose up --scale worker=N` works on one host. `./projects` and `cbc_cache` are already shared bind/volume mounts — do not scale workers onto a second node until storage is shared (Phase 2 below).
- Allow `ingest_pricebook` while an extraction runs; keep one extraction per project (already enforced).

**Phase 2 — horizontal workers**

- Move `projects/` to shared storage (EFS, NFS, or S3 + FUSE with local cache).
- Keep api + worker mounts pointed at the same root.
- Do **not** scale workers until storage is shared; otherwise uploads land on one node and the worker on another sees an empty `uploads/raw/`.

**Phase 3 — queue service (optional)**

- Replace poll loop with Redis Streams or SQS for lower enqueue latency than `WORKER_POLL_SECONDS`.
- Retain MongoDB as system of record; queue holds only job ids.

## Dashboard N+1 queries

[`apps/api/routers/projects.py`](../apps/api/routers/projects.py) `_decorate()` runs ~6 queries per project on `GET /api/projects`. At 50 bids this is ~300 round-trips.

**Recommended fix**

1. Add a `$lookup`-based aggregation on `list_projects` that returns counts in one pipeline.
2. Or maintain denormalized counters on the project document, updated in [`src/cbc/services/sync.py`](../src/cbc/services/sync.py) after each import.

**Alternates listing** ([`apps/api/routers/alternates.py`](../apps/api/routers/alternates.py)) has a similar per-group loop; collapse with `$group` on `alternateGroup`.

## Price book ingest throughput

[`apps/worker/handlers/ingest.py`](../apps/worker/handlers/ingest.py) upserts products one at a time. For large sheets, switch to `bulk_write` in batches of 500–1000 documents.

## MCP memory

There is a per-process PDF text cache at `.cache/pdftext.db` (WAL mode, shared `cbc_cache` volume). The five MCP servers (`pdf-tools`, `catalog`, `calc-engine`, `artifact-storage`, `p21-connector`) are stdio processes started per job. Catalog `find_pages` keeps an in-process LRU keyed on query + `builtAt`. Rendered pages are derived files under `/app/.cache`.

## Configuration reference

| Variable | Default | Notes |
|----------|---------|-------|
| `WORKER_CONCURRENCY` | `1` | Jobs this process may run at once |
| `WORKER_POLL_SECONDS` | `5` | Enqueue-to-start latency bound |
| `WORKER_JOB_TIMEOUT_SECONDS` | `3600` | Raise for large CAD sets before blaming the model |
| `WORKER_MAX_ATTEMPTS` | `3` | Failed jobs re-queue until cap |
| `INTERNAL_API_TOKEN` | falls back to `APP_SECRET_KEY` | Must match between web and api |

## Security before production scale

- API requires `X-Internal-Token` + `X-Actor` on all routes except `/api/health` and `/api/auth/verify` ([`apps/api/deps.py`](../apps/api/deps.py)).
- Do not expose port `8001` publicly; only the Next.js proxy should reach the API.
