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
import logging
import os
import signal
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from api import db as db_module  # noqa: E402
from api.db import db  # noqa: E402
from api.services import audit, provider, quote as quote_service, storage, sync  # noqa: E402
from cbc_core import claude_cli as runner, streaming  # noqa: E402
from scripts.validate_project import validate_job_artifacts  # noqa: E402
from worker import prompts  # noqa: E402
from worker.handlers.catalog import delete_catalog, index_catalog  # noqa: E402
from worker.handlers.document_index import delete_document, index_document  # noqa: E402
from worker.handlers.ingest import ingest_pricebook  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S"
)
log = logging.getLogger("cbc.worker")

POLL_SECONDS = int(os.environ.get("WORKER_POLL_SECONDS", "5"))
JOB_TIMEOUT = int(os.environ.get("WORKER_JOB_TIMEOUT_SECONDS", "3600"))
MAX_ATTEMPTS = int(os.environ.get("WORKER_MAX_ATTEMPTS", "3"))
# A bound on how far a pass can wander. A run that needs more than this has
# lost the thread, and stopping it is cheaper than letting it finish.
MAX_TURNS = int(os.environ.get("WORKER_MAX_TURNS", "60"))

# A full Phase 0-6 run is nine subagent calls plus the sheet-finding that feeds
# them, on a set that can be 744 pages. Both budgets above are sized for one phase
# and are simply wrong for six.
PIPELINE_TIMEOUT = int(os.environ.get("WORKER_PIPELINE_TIMEOUT_SECONDS", "10800"))
PIPELINE_MAX_TURNS = int(os.environ.get("WORKER_PIPELINE_MAX_TURNS", "200"))


def limits_for(job_type: str) -> tuple[int, int]:
    """(timeout seconds, max turns) for a job type."""
    if job_type == "run_full_pipeline":
        return PIPELINE_TIMEOUT, PIPELINE_MAX_TURNS
    return JOB_TIMEOUT, MAX_TURNS


# Which phase a project has reached, read from what is on disk. An autopilot run is
# one job that can last an hour, and `stage` is only written when a job finishes -
# so without this the board would sit on "intake / 0%" for the whole run.
PIPELINE_PROGRESS = (
    ("review/review_summary.html", "proposal", 95, "Review"),
    ("quotation.html", "proposal", 85, "Quote built"),
    ("priced/line_items.json", "quote", 70, "Pricing"),
    ("extracted/hardware_sets.json", "quote", 55, "Product matching"),
    ("extracted/door_schedule.json", "extraction", 40, "Take-off"),
    ("extracted/scope_summary.json", "extraction", 25, "Spec scoping"),
    ("extracted/scope_metadata.json", "intake", 10, "Intake"),
)


def phase_reached(project_dir: Path) -> tuple[str, int, str] | None:
    """The furthest phase whose output exists, or None if nothing has landed."""
    for relative, stage, progress, label in PIPELINE_PROGRESS:
        if (project_dir / relative).exists():
            return stage, progress, label
    return None

# A running job says so every HEARTBEAT_SECONDS. Nothing else distinguishes "this
# is a 40-minute extraction" from "the worker that claimed this was killed an hour
# ago", and without that distinction a dead job holds the exclusive-job index
# against its project forever.
HEARTBEAT_SECONDS = 30
STALE_AFTER = HEARTBEAT_SECONDS * 3

# Retry delay: RETRY_BASE * 2**attempts. Without it a job that fails in two
# seconds burns its whole attempt budget in six.
RETRY_BASE_SECONDS = int(os.environ.get("WORKER_RETRY_BASE_SECONDS", "30"))

_stop = asyncio.Event()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def claim() -> dict | None:
    """Atomically take the oldest due job. Two workers cannot take the same one."""
    now = _now()
    return await db.jobs.find_one_and_update(
        {
            "status": "queued",
            # A requeued job carries a delay; a fresh one has no such field.
            "$or": [{"nextAttemptAt": None}, {"nextAttemptAt": {"$lte": now}}],
        },
        {
            "$set": {"status": "running", "startedAt": now, "heartbeatAt": now},
            "$inc": {"attempts": 1},
        },
        sort=[("createdAt", 1)],
        return_document=True,
    )


async def reap_abandoned() -> int:
    """Recover jobs whose worker died while holding them.

    A `running` job with a stale heartbeat is not running: the process that
    claimed it is gone. Left alone it stays `running` forever, and because the
    exclusive-active-job index counts it as in flight, every later job of that
    type for that bid is silently handed back this corpse instead of being
    queued - the bid can never be re-extracted through the UI again.
    """
    cutoff = _now() - timedelta(seconds=STALE_AFTER)
    abandoned = await db.jobs.find(
        {
            "status": "running",
            "$or": [{"heartbeatAt": {"$lt": cutoff}}, {"heartbeatAt": None}],
        }
    ).to_list(100)

    for job in abandoned:
        attempts = job.get("attempts", 1)
        retry = attempts < MAX_ATTEMPTS
        await db.jobs.update_one(
            {"_id": job["_id"], "status": "running"},
            {
                "$set": {
                    "status": "queued" if retry else "failed",
                    "error": "worker stopped while this job was running",
                    "nextAttemptAt": _now() if retry else None,
                    "heartbeatAt": None,
                    "finishedAt": None if retry else _now(),
                }
            },
        )
        await audit.record(
            f"job.reaped.{job['type']}",
            actor="worker",
            target={"jobId": job["_id"], "projectId": job.get("projectId")},
            note="requeued" if retry else "attempts exhausted",
        )
        log.warning(
            "reaped abandoned %s (attempt %s) - %s",
            job["type"], attempts, "requeued" if retry else "failed",
        )
    return len(abandoned)


async def _beat(job_id) -> None:
    """Say the job is still alive until this task is cancelled."""
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        await db.jobs.update_one({"_id": job_id}, {"$set": {"heartbeatAt": _now()}})


async def finish(
    job: dict,
    ok: bool,
    error: str | None,
    output: str,
    note: str = "",
    permanent: bool = False,
    error_code: str | None = None,
) -> None:
    current = await db.jobs.find_one({"_id": job["_id"]}, {"status": 1})
    if current and current.get("status") == "cancelled":
        await db.jobs.update_one(
            {"_id": job["_id"]},
            {
                "$set": {
                    "log": (output or "")[-8000:],
                    "note": note or error or "cancelled by estimator",
                    "finishedAt": _now(),
                }
            },
        )
        await audit.record(
            f"job.cancelled.{job['type']}",
            actor="claude",
            target={"jobId": job["_id"], "projectId": job.get("projectId")},
            note=error or note,
        )
        log.info("job %s cancelled - left as cancelled", job["type"])
        return

    if error == "cancelled by estimator":
        await db.jobs.update_one(
            {"_id": job["_id"]},
            {
                "$set": {
                    "status": "cancelled",
                    "error": error,
                    "log": (output or "")[-8000:],
                    "note": note or None,
                    "finishedAt": _now(),
                }
            },
        )
        await audit.record(
            f"job.cancelled.{job['type']}",
            actor="claude",
            target={"jobId": job["_id"], "projectId": job.get("projectId")},
        )
        log.info("job %s cancelled during run", job["type"])
        return

    attempts = job.get("attempts", 1)
    retryable = not ok and not permanent and attempts < MAX_ATTEMPTS
    status = "queued" if retryable else ("done" if ok else "failed")

    await db.jobs.update_one(
        {"_id": job["_id"]},
        {
                "$set": {
                    "status": status,
                    "error": error,
                    "errorCode": error_code,
                    "log": (output or "")[-8000:],
                "note": note or None,
                "heartbeatAt": None,
                "nextAttemptAt": (
                    _now() + timedelta(seconds=RETRY_BASE_SECONDS * 2**attempts)
                    if retryable
                    else None
                ),
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
        log.warning(
            "job %s failed, retrying in %ss (attempt %s): %s",
            job["type"], RETRY_BASE_SECONDS * 2**attempts, attempts, error,
        )
    elif permanent and not ok:
        log.error("job %s FAILED permanently (not retried): %s", job["type"], error)
    elif ok:
        log.info("job %s done - %s", job["type"], note or "no changes reported")
    else:
        log.error("job %s FAILED: %s", job["type"], error)


async def sync_results(job: dict, project: dict | None) -> str:
    """Move what Claude wrote on disk into Mongo."""
    if project is None:
        return ""

    slug = project["slug"]
    if job["type"] in (
        "extract_bid_set",
        "rerun_extraction",
        "match_and_price",
        "build_proposal",
    ):
        validate_job_artifacts(job["type"], slug)

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
        # Store the totals here, because the quote screen no longer does it on
        # read (api/services/quote.py). Landing new priced lines is a change, so
        # this is the moment they are rolled up - otherwise the board would show
        # a stale quote total until somebody happened to open the bid.
        await quote_service.persist(project)
        await db.projects.update_one(
            {"_id": project["_id"]},
            {"$set": {"stage": "quote", "progress": 67, "updatedAt": _now()}},
        )
        return f"{counts['inserted']} priced, {counts['updated']} updated, {counts['skipped']} kept"

    if job["type"] == "run_full_pipeline":
        # One session produced all of it, so all of it lands at once - the same
        # three imports the gated path does at its three phase boundaries.
        openings = await sync.import_extraction(project)
        await db.documents.update_many(
            {"projectId": project["_id"]}, {"$set": {"state": "read"}}
        )
        priced = await sync.import_quote_lines(project)
        # Totals are stored on a change, not on a read (api/services/quote.py), and
        # new priced lines are a change - otherwise the board shows no value until
        # somebody opens the bid.
        await quote_service.persist(project)
        artifacts = await sync.import_proposal_artifacts(project)
        await db.projects.update_one(
            {"_id": project["_id"]},
            {"$set": {"stage": "proposal", "progress": 100, "phase": "Draft ready",
                      "updatedAt": _now()}},
        )
        written = sum(1 for present in artifacts.values() if present)
        return (
            f"{openings['inserted'] + openings['updated']} opening(s), "
            f"{priced['inserted'] + priced['updated']} priced line(s), "
            f"{written} proposal artifact(s) - draft ready for estimator review"
        )

    if job["type"] == "build_proposal":
        artifacts = await sync.import_proposal_artifacts(project)
        await db.projects.update_one(
            {"_id": project["_id"]},
            {"$set": {"stage": "proposal", "progress": 100, "updatedAt": _now()}},
        )
        written = sum(1 for present in artifacts.values() if present)
        return f"{written} proposal artifact(s) synced from disk"

    if job["type"] == "ingest_addendum":
        counts = await sync.import_addendum(project, job)
        return (
            f"{counts['added']} added, {counts['removed']} removed, "
            f"{counts['changed']} changed in addendum diff"
        )

    return ""


# Jobs the worker performs itself. Indexing a price book is deterministic
# extraction into SQLite - there is no reasoning in it, so spending a Claude pass
# (and its minutes, and its tokens) on it would be waste.
LOCAL_HANDLERS = {
    "index_catalog": index_catalog,
    "delete_catalog": delete_catalog,
    "index_document": index_document,
    "delete_document": delete_document,
}


async def process_locally(job: dict) -> None:
    """Run a job in this process rather than through a Claude Code pass."""
    handler = LOCAL_HANDLERS[job["type"]]
    heartbeat = asyncio.create_task(_beat(job["_id"]))
    try:
        note = await handler(job)
    except Exception as exc:
        log.exception("%s failed", job["type"])
        # A bad payload, a missing file, or a layout the extractor cannot read all
        # read exactly the same way on the third attempt. Retrying them spends the
        # attempt budget to reach the same conclusion more slowly.
        from catalog_index.pipeline import IndexingError
        from document_index.pipeline import IndexingError as DocumentIndexingError

        permanent = isinstance(
            exc, (ValueError, FileNotFoundError, IndexingError, DocumentIndexingError)
        )
        await finish(job, False, str(exc), "", permanent=permanent)
        return
    finally:
        heartbeat.cancel()
    await finish(job, True, None, "", note)


async def process(job: dict) -> None:
    if job["type"] in LOCAL_HANDLERS:
        await process_locally(job)
        return

    project = None
    if job.get("projectId"):
        project = await db.projects.find_one({"_id": job["projectId"]})
        if project is None:
            await finish(job, False, "project no longer exists", "")
            return
        storage.scaffold(project["slug"])

    payload = job.setdefault("payload", {})
    if job["type"] == "ingest_pricebook":
        # Assigned, never defaulted. `POST /api/jobs` takes a free-form payload, and
        # a `setdefault` here let the caller choose a path that the ingest handler
        # then read and unlinked - arbitrary file deletion through the jobs API.
        payload["outputPath"] = f".cache/pricebook-{job['_id']}.json"

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

    timeout, max_turns = limits_for(job["type"])
    cancel_event = threading.Event()

    async def watch_cancel() -> None:
        while not cancel_event.is_set():
            # A shutdown stops the subprocess the same way a cancel does. Without
            # this the container's grace period expires mid-run and the job is
            # SIGKILLed into a permanent `running`.
            if _stop.is_set():
                cancel_event.set()
                return
            doc = await db.jobs.find_one({"_id": job["_id"]}, {"status": 1})
            if doc and doc.get("status") == "cancelled":
                cancel_event.set()
                return
            await asyncio.sleep(1)

    async def watch_progress() -> None:
        """Move the bid along as each phase writes its output."""
        if job["type"] != "run_full_pipeline" or project is None:
            return
        directory = Path(storage.project_dir(project["slug"]))
        last: tuple[str, int, str] | None = None
        while True:
            reached = phase_reached(directory)
            if reached and reached != last:
                stage, progress, label = reached
                await db.projects.update_one(
                    {"_id": project["_id"]},
                    {"$set": {"stage": stage, "progress": progress,
                              "phase": label, "updatedAt": _now()}},
                )
                log.info("%s reached %s (%s%%)", project["code"], label, progress)
                last = reached
            await asyncio.sleep(10)

    watcher = asyncio.create_task(watch_cancel())
    heartbeat = asyncio.create_task(_beat(job["_id"]))
    progress_watcher = asyncio.create_task(watch_progress())
    try:
        result = await asyncio.to_thread(
            runner.run_claude,
            prompt,
            timeout,
            env,
            provider.secret_values(config),
            recording,
            job["type"],
            max_turns,
            _CATALOG_INDEX_PATH,
            cancel_event.is_set,
        )
    finally:
        cancel_event.set()
        watcher.cancel()
        heartbeat.cancel()
        progress_watcher.cancel()

    # Stopped because the worker is going down, not because anyone asked. Put it
    # back on the queue rather than recording a failure nobody caused.
    if _stop.is_set():
        current = await db.jobs.find_one({"_id": job["_id"]}, {"status": 1})
        if not current or current.get("status") != "cancelled":
            await db.jobs.update_one(
                {"_id": job["_id"]},
                {
                    "$set": {
                        "status": "queued",
                        "startedAt": None,
                        "heartbeatAt": None,
                        "nextAttemptAt": None,
                        "note": "worker shut down mid-run; requeued",
                    }
                },
            )
            log.info("job %s requeued for shutdown", job["type"])
            return

    # Recorded so "which provider produced this line?" is answerable months later,
    # the same question NFR-3 asks of every price.
    await db.jobs.update_one({"_id": job["_id"]}, {"$set": {"provider": described}})

    # And carried onto the bid itself when the provider is one Claude Code warns
    # about. A draft that looks finished but was produced on a model that could
    # not delegate is silently wrong at the level of the whole document - the
    # estimator has to be able to see that without reading the job log.
    if project is not None:
        degraded = bool(described.get("warnings"))
        await db.projects.update_one(
            {"_id": project["_id"]},
            {"$set": {
                "producedBy": {**described, "degraded": degraded},
                "degraded": degraded,
            }},
        )

    recording_note = ""
    if recording.exists():
        try:
            raw = recording.read_text(encoding="utf-8", errors="replace")
            rec_warnings = streaming.recording_warnings(raw)
            if rec_warnings:
                recording_note = "; ".join(rec_warnings)
        except OSError:
            pass
    if described.get("warnings"):
        provider_note = "; ".join(described["warnings"])
        recording_note = f"{recording_note}; {provider_note}" if recording_note else provider_note

    if not result.ok:
        await finish(
            job,
            False,
            result.error,
            result.output,
            permanent=result.permanent,
            error_code=result.error_code,
        )
        return

    try:
        note = (
            await ingest_pricebook(job)
            if job["type"] == "ingest_pricebook"
            else await sync_results(job, project)
        )
    except Exception as exc:  # a sync failure is a real failure - do not mask it
        await finish(job, False, f"result sync failed: {exc}", result.output, error_code="sync_failed")
        return

    combined = note
    if recording_note:
        combined = f"{note}; {recording_note}" if note else recording_note
    await finish(job, True, None, result.output, combined or None)


# Path to the SQLite catalog index for MCP pricing lookups.
_CATALOG_INDEX_PATH: str | None = os.environ.get("CATALOG_INDEX_PATH")


async def loop(once: bool = False) -> int:
    global _CATALOG_INDEX_PATH
    _CATALOG_INDEX_PATH = os.environ.get("CATALOG_INDEX_PATH")
    if _CATALOG_INDEX_PATH:
        log.info("catalog server will read index at %s", _CATALOG_INDEX_PATH)
    else:
        log.warning("CATALOG_INDEX_PATH is unset; catalog MCP lookups may return nothing")

    log.info(
        "worker up - polling every %ss (phase jobs %ss/%s turns, full pipeline %ss/%s turns)",
        POLL_SECONDS, JOB_TIMEOUT, MAX_TURNS, PIPELINE_TIMEOUT, PIPELINE_MAX_TURNS,
    )
    await reap_abandoned()

    while not _stop.is_set():
        job = await claim()
        if job:
            try:
                await process(job)
            except Exception as exc:
                # Without this, one unexpected exception ends the worker with the
                # job still marked `running` - which the reaper would eventually
                # recover, but only after the container came back. Record it now.
                log.exception("job %s raised", job["type"])
                try:
                    await finish(job, False, f"worker error: {exc}", "")
                except Exception:
                    log.exception("could not record the failure for job %s", job["_id"])
            if once:
                return 0
            continue
        if once:
            log.info("no queued jobs")
            return 0
        await reap_abandoned()
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
        for warning in described.get("warnings", []):
            print(f"PREFLIGHT WARN - {warning}")
        return 0

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: _stop.set())
        except (ValueError, OSError):  # not available on every platform/thread
            pass

    return asyncio.run(loop(args.once))


if __name__ == "__main__":
    sys.exit(main())
