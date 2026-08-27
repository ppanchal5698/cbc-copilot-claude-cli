#!/usr/bin/env python3
"""CBC Ops-Hub job worker.

Claims queued jobs, runs a headless Claude Code pass, then syncs what Claude
wrote on disk into MongoDB for the UI to serve.

    python worker/main.py              # run the loop
    python worker/main.py --once       # process at most one job, then exit
    python worker/main.py --preflight  # check the Claude CLI is usable
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from api import db as db_module  # noqa: E402
from api.db import db  # noqa: E402
from api.services import audit, provider, storage, sync  # noqa: E402
from worker import prompts, runner, streaming  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S"
)
log = logging.getLogger("cbc.worker")

POLL_SECONDS = int(os.environ.get("WORKER_POLL_SECONDS", "5"))
JOB_TIMEOUT = int(os.environ.get("WORKER_JOB_TIMEOUT_SECONDS", "1800"))
MAX_ATTEMPTS = int(os.environ.get("WORKER_MAX_ATTEMPTS", "3"))
# A bound on how far a pass can wander. A run that needs more than this has
# lost the thread, and stopping it is cheaper than letting it finish.
MAX_TURNS = int(os.environ.get("WORKER_MAX_TURNS", "60"))

_stop = asyncio.Event()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def claim() -> dict | None:
    """Atomically take the oldest queued job. Two workers cannot take the same one."""
    return await db.jobs.find_one_and_update(
        {"status": "queued"},
        {"$set": {"status": "running", "startedAt": _now()}, "$inc": {"attempts": 1}},
        sort=[("createdAt", 1)],
        return_document=True,
    )


async def finish(job: dict, ok: bool, error: str | None, output: str, note: str = "") -> None:
    retryable = not ok and job.get("attempts", 1) < MAX_ATTEMPTS
    status = "queued" if retryable else ("done" if ok else "failed")

    await db.jobs.update_one(
        {"_id": job["_id"]},
        {
            "$set": {
                "status": status,
                "error": error,
                "log": (output or "")[-8000:],
                "note": note or None,
                "finishedAt": None if retryable else _now(),
            }
        },
    )
    await audit.record(
        f"job.{status}.{job['type']}",
        actor="claude",
        target={"jobId": job["_id"], "projectId": job.get("projectId")},
        note=error or note or None,
    )

    if retryable:
        log.warning("job %s failed, requeued (attempt %s): %s", job["type"], job["attempts"], error)
    elif ok:
        log.info("job %s done - %s", job["type"], note or "no changes reported")
    else:
        log.error("job %s FAILED: %s", job["type"], error)


async def sync_results(job: dict, project: dict | None) -> str:
    """Move what Claude wrote on disk into Mongo."""
    if project is None:
        return ""

    if job["type"] in ("extract_bid_set", "rerun_extraction"):
        counts = await sync.import_extraction(project)
        await db.documents.update_many(
            {"projectId": project["_id"]}, {"$set": {"state": "read"}}
        )
        await db.projects.update_one(
            {"_id": project["_id"]},
            {"$set": {"stage": "extraction", "progress": 33, "updatedAt": _now()}},
        )
        return (
            f"{counts['inserted']} new, {counts['updated']} updated, "
            f"{counts['skipped']} left as the estimator set them"
        )

    if job["type"] == "match_and_price":
        counts = await sync.import_quote_lines(project)
        return f"{counts['inserted']} priced, {counts['updated']} updated, {counts['skipped']} kept"

    if job["type"] == "build_proposal":
        return "proposal artifacts written"

    return ""


async def ingest_pricebook(job: dict) -> str:
    """Load the parts Claude read off a price book into the catalog."""
    payload = job.get("payload") or {}
    output_path = REPO_ROOT / payload.get("outputPath", ".cache/pricebook-ingest.json")
    if not output_path.exists():
        return "no ingest file produced"

    data = json.loads(output_path.read_text(encoding="utf-8"))
    from bson import ObjectId

    book_id = ObjectId(payload["priceBookId"])
    written = 0
    for product in data.get("products", []):
        if not product.get("part"):
            continue
        await db.products.update_one(
            {"part": product["part"]},
            {
                "$set": {
                    "description": product.get("description", ""),
                    "manufacturer": product.get("manufacturer"),
                    "division": product.get("division"),
                    "listPrice": product.get("list_price"),
                    "multiplier": product.get("multiplier"),
                    "cost": product.get("cost"),
                    "priceBookId": book_id,
                    "sourcePage": product.get("source_page"),
                    "seedSource": "price book ingest",
                    "updatedAt": _now(),
                    "updatedBy": "claude",
                },
                "$setOnInsert": {"part": product["part"], "createdAt": _now()},
            },
            upsert=True,
        )
        written += 1

    await db.price_books.update_one(
        {"_id": book_id},
        {
            "$set": {
                "partCount": await db.products.count_documents({"priceBookId": book_id}),
                "effective": data.get("effective_date"),
                "lastIngestedAt": _now(),
            }
        },
    )
    output_path.unlink(missing_ok=True)
    return f"{written} parts written to the catalog"


async def process(job: dict) -> None:
    project = None
    if job.get("projectId"):
        project = await db.projects.find_one({"_id": job["projectId"]})
        if project is None:
            await finish(job, False, "project no longer exists", "")
            return
        storage.scaffold(project["slug"])

    payload = job.setdefault("payload", {})
    if job["type"] == "ingest_pricebook":
        payload.setdefault("outputPath", f".cache/pricebook-{job['_id']}.json")

    # Read the provider on every job, so changing it on the settings screen takes
    # effect on the next job rather than on the next worker restart.
    config = await db.settings.find_one({"_id": "claude"}) or provider.default_config()
    env, _ = provider.build_env(config)
    described = provider.describe(config)

    log.info(
        "running %s%s via %s (%s)",
        job["type"],
        f" for {project['code']}" if project else "",
        described["mode"],
        described["model"],
    )
    prompt = prompts.build(job, project)

    # Where the estimator watches this happen. Recorded per job under the project
    # so the session can be replayed after the fact, not only while it runs.
    recording = streaming.recording_path(
        project["slug"] if project else None, str(job["_id"]), REPO_ROOT
    )
    await db.jobs.update_one(
        {"_id": job["_id"]},
        {"$set": {"recording": str(recording.relative_to(REPO_ROOT)).replace("\\", "/")}},
    )

    result = await asyncio.to_thread(
        runner.run_claude,
        prompt,
        JOB_TIMEOUT,
        env,
        provider.secret_values(config),
        recording,
        job["type"],
        MAX_TURNS,
        _CATALOG_URI,
    )

    # Recorded so "which provider produced this line?" is answerable months later,
    # the same question NFR-3 asks of every price.
    await db.jobs.update_one({"_id": job["_id"]}, {"$set": {"provider": described}})

    if not result.ok:
        await finish(job, False, result.error, result.output)
        return

    try:
        note = (
            await ingest_pricebook(job)
            if job["type"] == "ingest_pricebook"
            else await sync_results(job, project)
        )
    except Exception as exc:  # a sync failure is a real failure - do not mask it
        await finish(job, False, f"result sync failed: {exc}", result.output)
        return

    await finish(job, True, None, result.output, note)


# Resolved once at startup; the catalog server is the only thing in a run that
# gets database credentials, and they are read-only.
_CATALOG_URI: str | None = None


async def loop(once: bool = False) -> int:
    global _CATALOG_URI
    if await db_module.ensure_readonly_user():
        _CATALOG_URI = db_module.readonly_uri()
        log.info("catalog server will read as %s", db_module.READONLY_USER)
    else:
        _CATALOG_URI = None
        log.warning(
            "could not provision the read-only database user; the catalog server "
            "will inherit nothing and pricing lookups will fail. Set "
            "MONGODB_READONLY_URI, or grant the API rights to create a user."
        )

    log.info("worker up - polling every %ss (timeout %ss)", POLL_SECONDS, JOB_TIMEOUT)
    while not _stop.is_set():
        job = await claim()
        if job:
            await process(job)
            if once:
                return 0
            continue
        if once:
            log.info("no queued jobs")
            return 0
        try:
            await asyncio.wait_for(_stop.wait(), timeout=POLL_SECONDS)
        except asyncio.TimeoutError:
            pass
    log.info("worker stopped")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="process at most one job")
    parser.add_argument("--preflight", action="store_true", help="check the Claude CLI")
    args = parser.parse_args()

    if args.preflight:
        # Against the configured provider, not the shell that happens to be
        # running this. Checking the inherited environment reports a failure on a
        # correctly configured system, which is worse than not checking at all.
        async def check() -> tuple[str | None, dict]:
            config = await db.settings.find_one({"_id": "claude"}) or provider.default_config()
            env, _ = provider.build_env(config)
            problem = await asyncio.to_thread(
                runner.preflight, env, provider.secret_values(config)
            )
            return problem, provider.describe(config)

        problem, described = asyncio.run(check())
        if problem:
            print(f"PREFLIGHT FAILED ({described['mode']}): {problem}")
            return 1
        print(
            f"PREFLIGHT OK - {described['mode']} / {described['model']}; "
            "Claude Code is reachable and authenticated."
        )
        return 0

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: _stop.set())
        except (ValueError, OSError):  # not available on every platform/thread
            pass

    return asyncio.run(loop(args.once))


if __name__ == "__main__":
    sys.exit(main())
