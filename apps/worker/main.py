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
import socket
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

# This is an entry point run as a file (`python worker/main.py`), so sys.path[0]
# is this directory, not the repo. The root has to be derived from __file__ here,
# before any repo import - cbc_core.paths.repo_root() is not importable yet.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from cbc.core import envfile  # noqa: E402
from cbc.services import provider  # noqa: E402

envfile.apply_to_environ(skip=provider.MANAGED)

from cbc import db as db_module  # noqa: E402
from cbc.db import db  # noqa: E402
from cbc.schemas.common import EXCLUSIVE_JOB_TYPES
from cbc.services import audit, quote as quote_service, render, storage, sync  # noqa: E402
from cbc.services import manifests, matchcache, runmetrics, sheetmap  # noqa: E402
from cbc.core import claude_cli as runner, streaming  # noqa: E402
from cbc.core import logs  # noqa: E402
from cbc.validation import ArtifactValidationError, validate_job_artifacts  # noqa: E402
from cbc.validation import review as review_flags  # noqa: E402
from apps.worker import prompts  # noqa: E402
from apps.worker.handlers.catalog import delete_catalog, index_catalog  # noqa: E402
from apps.worker.handlers.ingest import ingest_pricebook  # noqa: E402

log = logs.configure("cbc.worker")

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


def concurrency_for(raw: str | None = None) -> int:
    """How many jobs this process may run at once. Default 1; junk and 0 become 1."""
    value = os.environ.get("WORKER_CONCURRENCY", "1") if raw is None else raw
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


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

# Identifies this process when claiming jobs. A stale reaper can hand the same
# job to another worker; finish() only writes when workerId and claimGeneration
# still match, so a slow worker cannot overwrite a faster one's terminal state.
WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"

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
            "$set": {
                "status": "running",
                "startedAt": now,
                "heartbeatAt": now,
                "workerId": WORKER_ID,
            },
            "$inc": {"attempts": 1, "claimGeneration": 1},
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

    reaped = 0
    while abandoned:
        for job in abandoned:
            attempts = job.get("attempts", 1)
            retry = attempts < MAX_ATTEMPTS
            result = await db.jobs.update_one(
                {
                    "_id": job["_id"],
                    "status": "running",
                    "claimGeneration": job.get("claimGeneration"),
                },
                {
                    "$set": {
                        "status": "queued" if retry else "failed",
                        "error": "worker stopped while this job was running",
                        "nextAttemptAt": _now() if retry else None,
                        "heartbeatAt": None,
                        "workerId": None,
                        "finishedAt": None if retry else _now(),
                    },
                    "$inc": {"claimGeneration": 1},
                },
            )
            if not result.matched_count:
                continue
            reaped += 1
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
        if len(abandoned) < 100:
            break
        abandoned = await db.jobs.find(
            {
                "status": "running",
                "$or": [{"heartbeatAt": {"$lt": cutoff}}, {"heartbeatAt": None}],
            }
        ).to_list(100)
    return reaped


async def _beat(job_id, worker_id: str, claim_gen: int) -> None:
    """Say the job is still alive until this task is cancelled.

    One unhandled exception here killed the task for the rest of the run, with
    the exception never retrieved. Ninety seconds later reap_abandoned saw a
    stale heartbeat and requeued a job that was still running, and another
    worker claimed it - two Claude passes over the same project directory,
    because of one transient Mongo blip during a forty-minute pipeline.
    """
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        try:
            await db.jobs.update_one(
                {"_id": job_id, "workerId": worker_id, "claimGeneration": claim_gen},
                {"$set": {"heartbeatAt": _now()}},
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - a missed beat is not fatal
            log.warning("heartbeat for job %s failed, will retry: %s", job_id, exc)


def _owns_job(job: dict, current: dict | None) -> bool:
    """True when this worker's claim is still the active one."""
    if not current:
        return False
    return (
        current.get("workerId") == job.get("workerId")
        and current.get("claimGeneration") == job.get("claimGeneration")
    )


async def _job_cancelled(job_id) -> bool:
    doc = await db.jobs.find_one({"_id": job_id}, {"status": 1})
    return bool(doc and doc.get("status") == "cancelled")


async def finish(
    job: dict,
    ok: bool,
    error: str | None,
    output: str,
    note: str = "",
    permanent: bool = False,
    error_code: str | None = None,
) -> None:
    current = await db.jobs.find_one(
        {"_id": job["_id"]},
        {"status": 1, "workerId": 1, "claimGeneration": 1},
    )
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

    if not _owns_job(job, current):
        log.warning(
            "job %s completion ignored - claim was reaped or taken by another worker",
            job["type"],
        )
        return

    attempts = job.get("attempts", 1)
    retryable = not ok and not permanent and attempts < MAX_ATTEMPTS
    status = "queued" if retryable else ("done" if ok else "failed")

    await db.jobs.update_one(
        {
            "_id": job["_id"],
            "workerId": job.get("workerId"),
            "claimGeneration": job.get("claimGeneration"),
        },
        {
                "$set": {
                    "status": status,
                    "error": error,
                    "errorCode": error_code,
                    "log": (output or "")[-8000:],
                "note": note or None,
                "heartbeatAt": None,
                "nextAttemptAt": (
                    _now() + timedelta(seconds=RETRY_BASE_SECONDS * 2 ** max(attempts - 1, 0))
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

    # Bound rather than formatted in: under LOG_FORMAT=json these are their own
    # keys, so "every failure of this job type on this project" is a query rather
    # than a regex over sentences.
    entry = logs.bind(
        log,
        job_id=str(job["_id"]),
        job_type=job["type"],
        project_id=str(job["projectId"]) if job.get("projectId") else None,
        attempt=attempts,
    )
    if retryable:
        entry.warning(
            "job %s failed, retrying in %ss (attempt %s): %s",
            job["type"],
            RETRY_BASE_SECONDS * 2 ** max(attempts - 1, 0),
            attempts,
            error,
        )
    elif permanent and not ok:
        entry.error("job %s FAILED permanently (not retried): %s", job["type"], error)
    elif ok:
        entry.info("job %s done - %s", job["type"], note or "no changes reported")
    else:
        entry.error("job %s FAILED: %s", job["type"], error)


def _derive_review_flags(job_type: str, slug: str) -> None:
    """Write the mechanical review findings before the summary is rendered.

    Reported rather than raised, like the renders: a project whose artifacts are
    too broken to derive flags from is a project whose flags the estimator most
    needs, and losing the job would take the rest of the pass with it.
    """
    try:
        count = review_flags.write_flags(slug)
        log.info("%s: %d review flag(s) derived", job_type, count)
    except Exception:
        log.exception("%s: could not derive review flags for %s", job_type, slug)


def _sync_blocking_pre(job: dict, project: dict) -> dict:
    """BBox measurement, frame depths, and artifact validation — all sync I/O."""
    slug = project["slug"]
    if job["type"] in ("extract_bid_set", "rerun_extraction", "run_full_pipeline"):
        attached, unmatched = sync.measure_bboxes(project)
        if attached or unmatched:
            log.info(
                "%s bbox: %d measured from the sheet, %d left null and flagged",
                project.get("code", slug), attached, unmatched,
            )
        derived, no_depth = sync.derive_frame_depths(project)
        if derived or no_depth:
            log.info(
                "%s frame depth: %d derived from wall type, %d flagged for review",
                project.get("code", slug), derived, no_depth,
            )

    if job["type"] in (
        "extract_bid_set",
        "rerun_extraction",
        "match_and_price",
        "build_proposal",
        "run_full_pipeline",
    ):
        return validate_job_artifacts(job["type"], slug) or {}
    return {}


def _sync_blocking_render(job_type: str, slug: str) -> list[str]:
    """Derive review flags and render proposal artifacts. Returns failure details."""
    _derive_review_flags(job_type, slug)
    failed: list[str] = []
    for result in (render.render_quotation(slug), render.render_review_summary(slug)):
        if not result.ok:
            log.warning("%s: %s", job_type, result.detail)
            failed.append(result.detail)
    return failed


async def _persist_phase_state(job: dict, slug: str, phase_state: dict) -> None:
    if not phase_state:
        return
    await asyncio.to_thread(manifests.stamp_phase, slug, phase_state)
    await db.jobs.update_one({"_id": job["_id"]}, {"$set": {"phaseState": phase_state}})
    job["phaseState"] = phase_state


async def _inherit_phase_state(job: dict, project: dict) -> dict:
    """Copy still-valid phases from the previous job on this bid (B-15)."""
    prev = await db.jobs.find_one(
        {
            "projectId": project["_id"],
            "_id": {"$ne": job["_id"]},
            "phaseState": {"$exists": True, "$ne": {}},
        },
        sort=[("finishedAt", -1), ("createdAt", -1)],
    )
    if not prev:
        return {}
    kept = manifests.reusable_phases(project["slug"], prev.get("phaseState") or {})
    if kept:
        await db.jobs.update_one({"_id": job["_id"]}, {"$set": {"phaseState": kept}})
    return kept


async def sync_results(job: dict, project: dict | None) -> str:
    """Move what Claude wrote on disk into Mongo."""
    if project is None:
        return ""

    if await _job_cancelled(job["_id"]):
        raise RuntimeError("cancelled by estimator")

    slug = project["slug"]
    try:
        phase_state = await asyncio.to_thread(_sync_blocking_pre, job, project)
    except ArtifactValidationError as exc:
        await _persist_phase_state(job, slug, exc.phase_state or {})
        if job["type"] in matchcache.JOB_TYPES:
            await asyncio.to_thread(matchcache.ingest, slug)
        raise
    await _persist_phase_state(job, slug, phase_state or {})
    if job["type"] in matchcache.JOB_TYPES:
        await asyncio.to_thread(matchcache.ingest, slug)

    if await _job_cancelled(job["_id"]):
        raise RuntimeError("cancelled by estimator")

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
        if await _job_cancelled(job["_id"]):
            raise RuntimeError("cancelled by estimator")
        counts = await sync.import_quote_lines(project)
        await quote_service.persist(project)
        await db.projects.update_one(
            {"_id": project["_id"]},
            {"$set": {"stage": "quote", "progress": 67, "updatedAt": _now()}},
        )
        return f"{counts['inserted']} priced, {counts['updated']} updated, {counts['skipped']} kept"

    if job["type"] == "run_full_pipeline":
        if await _job_cancelled(job["_id"]):
            raise RuntimeError("cancelled by estimator")
        openings = await sync.import_extraction(project)
        await db.documents.update_many(
            {"projectId": project["_id"]}, {"$set": {"state": "read"}}
        )
        if await _job_cancelled(job["_id"]):
            raise RuntimeError("cancelled by estimator")
        priced = await sync.import_quote_lines(project)
        await quote_service.persist(project)
        failed = await asyncio.to_thread(_sync_blocking_render, job["type"], slug)
        artifacts = await sync.import_proposal_artifacts(project)
        await db.projects.update_one(
            {"_id": project["_id"]},
            {"$set": {"stage": "proposal", "progress": 100, "phase": "Draft ready",
                      "updatedAt": _now()}},
        )
        written = sum(1 for present in artifacts.values() if present)
        note = (
            f"{openings['inserted'] + openings['updated']} opening(s), "
            f"{priced['inserted'] + priced['updated']} priced line(s), "
            f"{written} proposal artifact(s) - draft ready for estimator review"
        )
        return f"{note} ({'; '.join(failed)})" if failed else note

    if job["type"] == "build_proposal":
        if await _job_cancelled(job["_id"]):
            raise RuntimeError("cancelled by estimator")
        failed = await asyncio.to_thread(_sync_blocking_render, job["type"], slug)
        artifacts = await sync.import_proposal_artifacts(project)
        await db.projects.update_one(
            {"_id": project["_id"]},
            {"$set": {"stage": "proposal", "progress": 100, "updatedAt": _now()}},
        )
        written = sum(1 for present in artifacts.values() if present)
        note = f"{written} proposal artifact(s) synced from disk"
        return f"{note} ({'; '.join(failed)})" if failed else note

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
}


async def _record_runmetrics(
    job: dict,
    recording: Path,
    prompt: str,
    project: dict | None,
    described: dict | None,
    error_code: str | None = None,
) -> None:
    """Parse the Claude recording after every post-CLI finish(). Never raises."""
    try:
        current = await db.jobs.find_one(
            {"_id": job["_id"]},
            {"status": 1, "errorCode": 1, "startedAt": 1, "finishedAt": 1, "provider": 1},
        )
        merged = {**job, **(current or {})}
        await runmetrics.record(
            merged,
            recording,
            prompt=prompt,
            project=project,
            provider=described or merged.get("provider"),
            outcome_status=merged.get("status"),
            error_code=error_code or merged.get("errorCode"),
        )
    except Exception:
        log.exception("runmetrics failed for job %s", job.get("_id"))


async def process_locally(job: dict) -> None:
    """Run a job in this process rather than through a Claude Code pass."""
    handler = LOCAL_HANDLERS[job["type"]]
    heartbeat = asyncio.create_task(_beat(job["_id"], job.get("workerId", WORKER_ID), job.get("claimGeneration", 0)))
    try:
        note = await handler(job)
    except Exception as exc:
        log.exception("%s failed", job["type"])
        # A bad payload, a missing file, or a layout the extractor cannot read all
        # read exactly the same way on the third attempt. Retrying them spends the
        # attempt budget to reach the same conclusion more slowly.
        from apps.worker.handlers.catalog import IndexingError

        permanent = isinstance(exc, (ValueError, FileNotFoundError, IndexingError))
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

    # One Claude session per bid: if another pipeline job is still running on this
    # project, defer until it finishes (handles reaper/claim races).
    if (
        project is not None
        and job["type"] in EXCLUSIVE_JOB_TYPES
        and job.get("status") == "running"
    ):
        other = await db.jobs.find_one(
            {
                "projectId": project["_id"],
                "type": {"$in": list(EXCLUSIVE_JOB_TYPES)},
                "status": "running",
                "_id": {"$ne": job["_id"]},
            }
        )
        if other:
            log.info(
                "job %s (%s) blocked by concurrent pipeline job %s (%s)",
                job["_id"],
                job["type"],
                other["_id"],
                other["type"],
            )
            await db.jobs.update_one(
                {
                    "_id": job["_id"],
                    "status": "running",
                    "workerId": job.get("workerId"),
                    "claimGeneration": job.get("claimGeneration"),
                },
                {
                    "$set": {
                        "status": "queued",
                        "startedAt": None,
                        "heartbeatAt": None,
                        "workerId": None,
                        "nextAttemptAt": _now() + timedelta(seconds=15),
                        "note": (
                            f"waiting for {other['type']} job {other['_id']} "
                            "to finish (one session per bid)"
                        ),
                    },
                    "$inc": {"attempts": -1},
                },
            )
            return

    payload = job.setdefault("payload", {})
    if job["type"] == "ingest_pricebook":
        # Assigned, never defaulted. `POST /api/jobs` takes a free-form payload, and
        # a `setdefault` here let the caller choose a path that the ingest handler
        # then read and unlinked - arbitrary file deletion through the jobs API.
        payload["outputPath"] = f".cache/pricebook-{job['_id']}.json"

    # Catalog `force` reindexes a sheet; pipeline `force` means rebuild phases.
    # Do not mix the two.
    if (
        project is not None
        and job["type"] in sheetmap.SHEETMAP_JOB_TYPES | {"match_and_price", "build_proposal"}
        and payload.get("force")
    ):
        await db.jobs.update_one({"_id": job["_id"]}, {"$unset": {"phaseState": ""}})
        job.pop("phaseState", None)

    if (
        project is not None
        and job["type"] == "run_full_pipeline"
        and not payload.get("force")
    ):
        inherited = await _inherit_phase_state(job, project)
        if inherited:
            job["phaseState"] = inherited

    if project is not None and job["type"] in sheetmap.SHEETMAP_JOB_TYPES:
        await asyncio.to_thread(
            sheetmap.build_sheetmap,
            project["slug"],
            force=bool(payload.get("force")),
        )

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
    # A provider that cannot call the Agent tool is told to do the phases itself.
    # Handing it the delegating prompt is what produced a run that made seven tool
    # calls in twelve minutes and wrote nothing.
    delegates = provider.supports_subagents(config)
    if not delegates:
        log.info("provider cannot delegate; using the solo prompt for %s", job["type"])
    prompt = prompts.build(job, project, delegates=delegates)

    from cbc.db import readonly_uri

    if job["type"] in ("match_and_price", "ingest_pricebook") and not readonly_uri():
        await finish(
            job,
            False,
            "catalog unavailable: set MONGODB_READONLY_URI before pricing jobs",
            "",
            error_code="catalog_unavailable",
        )
        return

    # Where the estimator watches this happen. Recorded per job under the project
    # so the session can be replayed after the fact, not only while it runs.
    attempt = max(int(job.get("attempts") or 1), 1)
    recording = streaming.recording_path(
        project["slug"] if project else None,
        str(job["_id"]),
        REPO_ROOT,
        attempt=attempt,
    )
    if attempt > 1:
        await asyncio.to_thread(streaming.write_retry_banner, recording, attempt)
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
    heartbeat = asyncio.create_task(
        _beat(job["_id"], job.get("workerId", WORKER_ID), job.get("claimGeneration", 0))
    )
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
            cancel_event.is_set,
        )
    finally:
        cancel_event.set()
        watcher.cancel()
        heartbeat.cancel()
        progress_watcher.cancel()

    # Stopped because the worker is going down, not because anyone asked. Put it
    # back on the queue rather than recording a failure nobody caused.
    if _stop.is_set() and not result.ok:
        # Two guards finish() has always had and this did not.
        #
        # Ownership: an unfiltered write here requeued a job this worker no
        # longer held - reaped, re-claimed and already running elsewhere - so a
        # third worker picked it up and two Claude passes wrote
        # projects/{slug}/priced/line_items.json at once.
        #
        # And `result.ok`: a SIGTERM arriving after a successful run but before
        # finish() threw the completed pass away and decremented attempts, so a
        # three-hour extraction ran again from the start on restart.
        current = await db.jobs.find_one(
            {"_id": job["_id"]}, {"status": 1, "workerId": 1, "claimGeneration": 1}
        )
        if _owns_job(job, current) and current.get("status") != "cancelled":
            await db.jobs.update_one(
                {
                    "_id": job["_id"],
                    "workerId": job.get("workerId"),
                    "claimGeneration": job.get("claimGeneration"),
                },
                {
                    "$set": {
                        "status": "queued",
                        "startedAt": None,
                        "heartbeatAt": None,
                        "nextAttemptAt": None,
                        "workerId": None,
                        "note": "worker shut down mid-run; requeued",
                    },
                    "$inc": {"attempts": -1},
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
            raw = await asyncio.to_thread(
                recording.read_text, encoding="utf-8", errors="replace"
            )
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
        await _record_runmetrics(
            job, recording, prompt, project, described, result.error_code
        )
        return

    try:
        note = (
            await ingest_pricebook(job)
            if job["type"] == "ingest_pricebook"
            else await sync_results(job, project)
        )
    except ArtifactValidationError as exc:
        await finish(
            job,
            False,
            str(exc),
            result.output,
            permanent=True,
            error_code="artifact_validation",
        )
        await _record_runmetrics(
            job, recording, prompt, project, described, "artifact_validation"
        )
        return
    except Exception as exc:  # a sync failure is a real failure - do not mask it
        if str(exc) == "cancelled by estimator":
            await finish(job, False, "cancelled by estimator", result.output)
            await _record_runmetrics(job, recording, prompt, project, described)
            return
        await finish(job, False, f"result sync failed: {exc}", result.output, error_code="sync_failed")
        await _record_runmetrics(
            job, recording, prompt, project, described, "sync_failed"
        )
        return

    combined = note
    if recording_note:
        combined = f"{note}; {recording_note}" if note else recording_note
    await finish(job, True, None, result.output, combined or None)
    await _record_runmetrics(job, recording, prompt, project, described)


async def loop(once: bool = False) -> int:
    # The catalog server reads the page index from MongoDB with a credential that
    # cannot write, handed to it per job by cbc.core.toolsets. Say so if there is
    # none, because a pricing pass with no catalog flags every line MANUAL and
    # looks like a model failure rather than a missing credential.
    from cbc.db import readonly_uri

    if not readonly_uri():
        log.warning(
            "no read-only MongoDB credential; the catalog server will not be able "
            "to read the page index and pricing will fall back to manual entry"
        )

    log.info(
        "worker up - polling every %ss (phase jobs %ss/%s turns, full pipeline %ss/%s turns, concurrency %s)",
        POLL_SECONDS, JOB_TIMEOUT, MAX_TURNS, PIPELINE_TIMEOUT, PIPELINE_MAX_TURNS,
        1 if once else concurrency_for(),
    )
    await reap_abandoned()

    slots = 1 if once else concurrency_for()
    in_flight: set[asyncio.Task] = set()

    async def run_claimed(job: dict) -> None:
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

    while not _stop.is_set():
        while len(in_flight) < slots and not _stop.is_set():
            job = await claim()
            if not job:
                break
            in_flight.add(asyncio.create_task(run_claimed(job)))
            if once:
                break
        if in_flight:
            _done, in_flight = await asyncio.wait(
                in_flight, return_when=asyncio.FIRST_COMPLETED
            )
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
    if in_flight:
        await asyncio.wait(in_flight)
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
