"""Rendering the two HTML artifacts, deterministically.

`build_proposal` told `quote-builder` to run `validate_and_render_quote.py` and
`quality-reviewer` to run `render_review_summary.py`. Telling is not enforcing:
an agent that hand-writes the HTML instead produces a quotation that looks right
and was never checked against the pricing rules, and one that skips the step
produces nothing at all. `quality-reviewer` could not have run its script even
if it tried - `Bash` was not in its tool list.

So the worker runs both scripts itself after the pass, and whatever the agent
wrote is overwritten by the validated render. The agent still does the work only
it can do - the judgment, the flags, the RFI prose - and the arithmetic and the
markup come from code that does the same thing every time.

A failure here is reported, not raised: the pass may have produced a perfectly
good review with a quote that does not yet validate, and losing the whole job
over the render would throw away the part that worked.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

from cbc.core.paths import repo_root

REPO_ROOT = repo_root()

QUOTE_SCRIPT = REPO_ROOT / "scripts" / "validate_and_render_quote.py"
REVIEW_SCRIPT = REPO_ROOT / "scripts" / "render_review_summary.py"

# Long enough for a large quote, short enough that a hung render does not hold a
# worker slot until the job times out.
TIMEOUT_SECONDS = 180


@dataclass(frozen=True)
class RenderResult:
    ok: bool
    detail: str

    def __bool__(self) -> bool:
        return self.ok


def _run(script, slug: str, label: str) -> RenderResult:
    if not script.exists():
        return RenderResult(False, f"{label}: script missing at {script}")
    try:
        done = subprocess.run(
            [sys.executable, str(script), slug],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return RenderResult(False, f"{label}: timed out after {TIMEOUT_SECONDS}s")
    if done.returncode == 0:
        return RenderResult(True, f"{label}: rendered")
    # The scripts print their reasons to stderr, one per line, and those reasons
    # are the point - "line 14 has a cost with no sale_ea" is what the estimator
    # needs, not "exit 1".
    reason = (done.stderr or done.stdout or "").strip().splitlines()
    return RenderResult(False, f"{label}: {'; '.join(reason[-3:]) or 'failed'}")


def render_quotation(slug: str) -> RenderResult:
    """Validate the priced lines and render projects/{slug}/quotation.html."""
    return _run(QUOTE_SCRIPT, slug, "quotation")


def render_review_summary(slug: str) -> RenderResult:
    """Render projects/{slug}/review/review_summary.html from flags and lines."""
    return _run(REVIEW_SCRIPT, slug, "review summary")
