"""Invoking Claude Code headless.

One place in the system spawns `claude --print`. It captures the log, enforces a
timeout, and reports failure honestly rather than pretending a job succeeded.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
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


def run_claude(prompt: str, timeout: int = 1800) -> RunResult:
    """Run one headless Claude Code pass in the repo root.

    --dangerously-skip-permissions is used because an unattended run cannot
    answer prompts. The safety comes from the PreToolUse hooks, which fire
    regardless of permission mode and block every send and destructive delete.
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

    command = [binary, "--print", "--dangerously-skip-permissions", prompt]

    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
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

    output = (completed.stdout or "")[-MAX_LOG_CHARS:]
    stderr = (completed.stderr or "")[-MAX_LOG_CHARS:]

    # The CLI exits 0 on an auth failure, so the exit code alone is not enough.
    lowered = f"{output}\n{stderr}".lower()
    for marker in ("failed to authenticate", "oauth session expired", "invalid api key"):
        if marker in lowered:
            return RunResult(
                ok=False,
                output=output,
                error=(
                    "Claude Code could not authenticate. Sign in with the CLI "
                    "(`claude` interactively) and re-run this job."
                ),
                returncode=completed.returncode,
            )

    if completed.returncode != 0:
        return RunResult(
            ok=False,
            output=output,
            error=stderr.strip() or f"claude exited {completed.returncode}",
            returncode=completed.returncode,
        )

    return RunResult(ok=True, output=output, error=None, returncode=0)


def preflight() -> str | None:
    """Return a human-readable problem, or None when the CLI looks usable."""
    result = run_claude("Reply with exactly: WORKER_PREFLIGHT_OK", timeout=90)
    if not result.ok:
        return result.error
    if "WORKER_PREFLIGHT_OK" not in result.output:
        return f"unexpected reply from the CLI: {result.output[:200]!r}"
    return None
