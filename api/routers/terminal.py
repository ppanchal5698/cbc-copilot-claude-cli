"""Streaming a job's terminal recording to the browser.

The worker runs Claude Code on a pty and appends every byte to
`projects/{slug}/.runs/{job_id}.log`. Both containers share that volume, so the
API can tail the file without the two processes needing to talk to each other -
no broker, no socket between services, and it works the same on Fargate with EFS
behind it.

What goes down the wire is the recording verbatim: escape sequences included, so
xterm.js renders the session the CLI actually drew rather than a paraphrase of
it. Credentials are already stripped on the way in, by `worker/streaming.py`.
"""
from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.config import settings
from api.db import db, oid

router = APIRouter(prefix="/api/jobs/{job_id}/terminal", tags=["terminal"])

POLL_SECONDS = 0.4
IDLE_TIMEOUT = 900  # a stream with nothing to say for this long has been abandoned


async def _job(job_id: str) -> dict:
    job = await db.jobs.find_one({"_id": oid(job_id)})
    if not job:
        raise HTTPException(404, "job not found")
    return job


def _recording_of(job: dict) -> Path | None:
    relative = job.get("recording")
    if not relative:
        return None
    # Never let a stored path escape the project tree.
    path = (settings.repo_root / relative).resolve()
    if not str(path).startswith(str(settings.repo_root.resolve())):
        raise HTTPException(400, "recording path is outside the project tree")
    return path


@router.get("")
async def get_terminal(job_id: str) -> dict:
    """The whole recording so far, for replaying a finished run."""
    job = await _job(job_id)
    path = _recording_of(job)

    if path is None or not path.exists():
        return {
            "jobId": job_id,
            "status": job.get("status"),
            "available": False,
            "reason": (
                "This job ran before terminal recording existed."
                if job.get("status") in ("done", "failed", "cancelled")
                else "Nothing has been written yet."
            ),
            "data": "",
        }

    payload = path.read_bytes()
    return {
        "jobId": job_id,
        "status": job.get("status"),
        "available": True,
        "bytes": len(payload),
        # base64 so the escape sequences survive JSON intact.
        "data": base64.b64encode(payload).decode("ascii"),
    }


@router.get("/stream")
async def stream_terminal(job_id: str, offset: int = 0) -> StreamingResponse:
    """Server-sent events carrying the recording as it is written.

    `offset` lets a reconnecting browser resume where it left off instead of
    replaying the whole session.
    """
    job = await _job(job_id)
    path = _recording_of(job)

    async def events() -> AsyncIterator[bytes]:
        position = offset
        idle = 0.0

        while True:
            current = await _job(job_id)
            finished = current.get("status") in ("done", "failed", "cancelled")
            target = _recording_of(current)

            if target and target.exists():
                size = target.stat().st_size
                if size < position:
                    # The file was replaced - a re-run of the same job.
                    position = 0
                if size > position:
                    with target.open("rb") as handle:
                        handle.seek(position)
                        chunk = handle.read(size - position)
                    position += len(chunk)
                    idle = 0.0
                    encoded = base64.b64encode(chunk).decode("ascii")
                    yield f"event: output\ndata: {encoded}\n\n".encode("utf-8")

            if finished:
                yield (
                    f"event: end\ndata: {current.get('status')}\n\n"
                ).encode("utf-8")
                return

            await asyncio.sleep(POLL_SECONDS)
            idle += POLL_SECONDS
            if idle >= IDLE_TIMEOUT:
                yield b"event: end\ndata: idle\n\n"
                return
            if idle % 15 < POLL_SECONDS:
                # Keeps proxies from closing a quiet connection mid-run.
                yield b": keep-alive\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
