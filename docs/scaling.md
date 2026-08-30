# Ops-Hub scaling guide

This document captures the current throughput ceiling and the changes needed
before multiple estimators can run the pipeline concurrently in production.

## Current architecture limits

| Layer | Constraint | Symptom |
|-------|------------|---------|
| Worker | Single `cbc-worker` container, serial `process()` loop | One Claude pass blocks all other jobs |
| Filesystem | `projects/` bind mount shared only between api + worker on one host | Second worker on another node cannot read PDFs |
| MongoDB | Single instance, no sharding | Dashboard/list queries scale with bid count |
| Job queue | Global FIFO (oldest queued job first) | Price book ingest waits behind long extractions |

## Worker concurrency (recommended path)

**Phase 1 — same host, typed concurrency**

- Run multiple worker processes in one container (or increase replicas with shared volume).
- Keep `claim()` atomic; add optional `WORKER_CONCURRENCY` env (default `1`).
- Partition by job type: allow `ingest_pricebook` while `extract_bid_set` runs, but keep one extraction per project (already enforced by partial unique index on `(projectId, type)` for active jobs).

**Phase 2 — horizontal workers**

- Move `projects/` to shared storage (EFS, NFS, or S3 + FUSE with local cache).
- Keep api + worker mounts pointed at the same root.
- Do **not** scale workers until storage is shared; otherwise uploads land on one node and the worker on another sees an empty `uploads/raw/`.

**Phase 3 — queue service (optional)**

- Replace poll loop with Redis Streams or SQS for lower enqueue latency than `WORKER_POLL_SECONDS`.
- Retain MongoDB as system of record; queue holds only job ids.

## Dashboard N+1 queries

[`api/routers/projects.py`](../api/routers/projects.py) `_decorate()` runs ~6 queries per project on `GET /api/projects`. At 50 bids this is ~300 round-trips.

**Recommended fix**

1. Add a `$lookup`-based aggregation on `list_projects` that returns counts in one pipeline.
2. Or maintain denormalized counters on the project document, updated in [`api/services/sync.py`](../api/services/sync.py) after each import.

**Alternates listing** ([`api/routers/alternates.py`](../api/routers/alternates.py)) has a similar per-group loop; collapse with `$group` on `alternateGroup`.

## Price book ingest throughput

[`worker/handlers/ingest.py`](../worker/handlers/ingest.py) upserts products one at a time. For large sheets, switch to `bulk_write` in batches of 500–1000 documents.

## MCP memory

[`mcp-servers/pricebook/server.py`](../mcp-servers/pricebook/server.py) caches full PDF page text per process. Long pricing jobs with multiple large books should use an LRU byte cap or on-disk cache outside `pricebooks/`.

## Configuration reference

| Variable | Default | Notes |
|----------|---------|-------|
| `WORKER_POLL_SECONDS` | `5` | Enqueue-to-start latency bound |
| `WORKER_JOB_TIMEOUT_SECONDS` | `3600` | Raise for large CAD sets before blaming the model |
| `WORKER_MAX_ATTEMPTS` | `3` | Failed jobs re-queue until cap |
| `INTERNAL_API_TOKEN` | falls back to `APP_SECRET_KEY` | Must match between web and api |

## Security before production scale

- API requires `X-Internal-Token` + `X-Actor` on all routes except `/api/health` and `/api/auth/verify` ([`api/deps.py`](../api/deps.py)).
- Do not expose port `8001` publicly; only the Next.js proxy should reach the API.
