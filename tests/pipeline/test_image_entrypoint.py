"""The container entrypoint has to be executable, and git has to know it.

`docker/entrypoint.sh` was committed 100644. Windows checkouts run with
core.fileMode=false, so the execute bit is never tracked from there, and Docker
Desktop starts the container anyway - which is why this survived every local
`docker compose up`. On a Linux host the COPY preserves 644 and the container
dies at start with:

    exec: "/app/docker/entrypoint.sh": permission denied

Nothing built the image in CI until the e2e job existed, so the image had never
in fact been runnable from a clean Linux checkout.

Two independent guards, because either can be defeated on its own: the mode in
git, and a chmod in the Dockerfile that holds whatever the checkout did.
"""
from __future__ import annotations

import subprocess

import pytest

from tests.shared import ROOT

ENTRYPOINT = "docker/entrypoint.sh"


def _tracked_mode(path: str) -> str:
    out = subprocess.run(
        ["git", "ls-files", "-s", "--", path],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if not out:
        pytest.skip(f"{path} is not tracked by git here")
    return out.split()[0]


def test_the_entrypoint_is_executable_in_git() -> None:
    """A Windows checkout will not set this for you - it must be in the index."""
    assert _tracked_mode(ENTRYPOINT) == "100755", (
        f"{ENTRYPOINT} is committed non-executable; the container cannot start "
        "on a Linux host. Fix with: git update-index --chmod=+x " + ENTRYPOINT
    )


def test_the_dockerfile_does_not_rely_on_the_checkout() -> None:
    """The belt to the index's braces.

    A future contributor on a filesystem that drops the bit, or a build context
    assembled by something other than git, must still produce a runnable image.
    """
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "chmod +x /app/docker/entrypoint.sh" in dockerfile


def test_the_entrypoint_is_the_only_script_the_image_execs_directly() -> None:
    """If another one is added, it needs the same two guards.

    Everything else is invoked as `bash script.sh` or `python module.py`, which
    does not care about the execute bit. ENTRYPOINT and CMD do.
    """
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    execd = [
        line
        for line in dockerfile.splitlines()
        if line.startswith(("ENTRYPOINT", "CMD")) and ".sh" in line
    ]
    assert execd == ['ENTRYPOINT ["/app/docker/entrypoint.sh"]'], execd
