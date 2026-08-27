"""Invoking Claude Code headless.

One place in the system spawns `claude --print`. It captures the log, enforces a
timeout, and reports failure honestly rather than pretending a job succeeded.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from api.services import secrets  # noqa: E402
MAX_LOG_CHARS = 20_000


def resolve_binary() -> str | None:
    """Find the Claude Code CLI.

    On Windows npm installs it as claude.cmd, which subprocess will not resolve
    from a bare name - shutil.which honours PATHEXT and finds it.
    """
    configured = os.environ.get("CLAUDE_BIN", "claude")
    if Path(configured).is_file():
        return configured
    found = shutil.which(configured)
    if found:
        return found
    for suffix in (".cmd", ".exe", ".ps1"):
        found = shutil.which(configured + suffix)
        if found:
            return found
    return None


@dataclass
class RunResult:
    ok: bool
    output: str
    error: str | None
    returncode: int


def run_claude(
    prompt: str,
    timeout: int = 1800,
    env: dict[str, str] | None = None,
    redact_values: list[str] | None = None,
    recording: "Path | None" = None,
    job_type: str | None = None,
    max_turns: int | None = None,
    catalog_uri: str | None = None,
) -> RunResult:
    """Run one headless Claude Code pass in the repo root.

    --dangerously-skip-permissions is used because an unattended run cannot
    answer prompts. The safety comes from the PreToolUse hooks, which fire
    regardless of permission mode and block every send and destructive delete.

    `env` comes from `api.services.provider.build_env`, so which provider serves
    a job is a configured choice rather than a property of the shell that
    happened to launch the worker. Passing None inherits the environment, which
    is what preflight from a terminal wants.
    """
    binary = resolve_binary()
    if binary is None:
        return RunResult(
            ok=False,
            output="",
            error=(
                f"Claude Code CLI not found as {os.environ.get('CLAUDE_BIN', 'claude')!r}. "
                "Set CLAUDE_BIN to its full path."
            ),
            returncode=127,
        )

    # Only the tools this phase uses, and a bound on how long it may go round.
    scope: list[str] = []
    if job_type:
        from worker import toolsets

        scope = toolsets.flags_for(job_type, catalog_uri)
    if max_turns:
        scope += ["--max-turns", str(max_turns)]

    command = [binary, "--print", *scope, "--dangerously-skip-permissions", prompt]

    # A recorded run narrates itself.
    #
    # `--print` alone emits only the final answer - on a pty, a whole extraction
    # produced 14 bytes - so there is nothing to watch during the minutes that
    # matter. `--output-format stream-json --verbose` makes the CLI report each
    # tool call as it makes it, which is the actual process output and the only
    # form of it that shows progress. (The interactive TUI would be richer still,
    # but it stops on the login-method screen and cannot be driven unattended.)
    if recording is not None:
        from worker import streaming

        streamed = [
            binary,
            "--print",
            "--verbose",
            "--output-format",
            "stream-json",
            *scope,
            "--dangerously-skip-permissions",
            prompt,
        ]
        try:
            returncode, raw = streaming.run_on_pty(
                streamed,
                cwd=REPO_ROOT,
                env=env,
                timeout=timeout,
                recording=recording,
                redact_values=redact_values,
            )
        except (ImportError, OSError) as exc:
            # No pty on this host; fall through to pipes rather than fail the job.
            returncode, raw = None, f"[terminal recording unavailable: {exc}]"
        if returncode is not None:
            text, failure = streaming.summarise(raw)
            return _interpret(text, failure, returncode, timeout, redact_values)

    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except FileNotFoundError:
        return RunResult(
            ok=False,
            output="",
            error=f"could not execute {binary!r}",
            returncode=127,
        )
    except subprocess.TimeoutExpired:
        return RunResult(
            ok=False, output="", error=f"timed out after {timeout}s", returncode=124
        )

    return _interpret(
        completed.stdout or "", completed.stderr or "", completed.returncode,
        timeout, redact_values,
    )


def _interpret(
    stdout: str,
    stderr: str,
    returncode: int,
    timeout: int,
    redact_values: list[str] | None,
) -> RunResult:
    """Turn a finished run into a verdict.

    Shared by the pty path and the pipe path, so "did this succeed?" has one
    answer however the process was spawned.
    """
    # Redact before anything else touches these: the caller stores the output on
    # the job document and the UI renders it.
    output = secrets.redact(stdout[-MAX_LOG_CHARS:], redact_values)
    errors = secrets.redact(stderr[-MAX_LOG_CHARS:], redact_values)

    if returncode == 124:
        return RunResult(
            ok=False, output=output, error=f"timed out after {timeout}s", returncode=124
        )

    # The CLI exits 0 on an auth failure, so the exit code alone is not enough.
    lowered = f"{output}\n{errors}".lower()
    for marker in ("failed to authenticate", "oauth session expired", "invalid api key"):
        if marker in lowered:
            return RunResult(
                ok=False,
                output=output,
                error=(
                    "Claude Code could not authenticate. Configure a provider on "
                    "the settings screen, or sign in with the CLI, then re-run."
                ),
                returncode=returncode,
            )

    if returncode != 0:
        return RunResult(
            ok=False,
            output=output,
            error=errors.strip() or f"claude exited {returncode}",
            returncode=returncode,
        )

    return RunResult(ok=True, output=output, error=None, returncode=0)


def preflight(
    env: dict[str, str] | None = None, redact_values: list[str] | None = None
) -> str | None:
    """Return a human-readable problem, or None when the CLI looks usable.

    This is also what the settings screen's Test connection button runs, so a
    misconfigured provider is reported the same way there as it is at startup -
    including the auth-marker scan, which exists because the CLI exits 0 on an
    authentication failure.
    """
    result = run_claude(
        "Reply with exactly: WORKER_PREFLIGHT_OK",
        timeout=90,
        env=env,
        redact_values=redact_values,
    )
    if not result.ok:
        return result.error
    if "WORKER_PREFLIGHT_OK" not in result.output:
        return f"unexpected reply from the CLI: {result.output[:200]!r}"
    return None
