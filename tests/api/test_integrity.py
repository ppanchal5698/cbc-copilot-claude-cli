"""Data-integrity and guardrail checks that need no database.

These cover the failures that only show up under concurrency, on a re-run, or on
a value that was already stored - the kind local development never produces.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from tests.shared import ROOT

# ── sync: identity keys must survive a re-run ───────────────────────────────


def test_repeated_marks_get_their_own_stable_keys() -> None:
    """A schedule really can list the same mark twice.

    Keying both on `mark:05` made each run insert two fresh rows and orphan the
    previous pair, because the lookup built before the loop only held one of them.
    """
    from api.services.sync import _distinct_keys, _identity

    openings = [{"mark": "01"}, {"mark": "05"}, {"mark": "05"}, {"mark": "07"}]
    keys = _distinct_keys(openings, _identity)

    assert keys == ["mark:01", "mark:05", "mark:05#2", "mark:07"]
    assert len(set(keys)) == len(keys), "keys collide within one payload"
    # Stable: the same schedule read again produces the same keys.
    assert _distinct_keys(openings, _identity) == keys


def test_priced_lines_key_on_content_not_position() -> None:
    """Re-ordering a re-priced quote must not duplicate every line."""
    from api.services.sync import _content_key, _distinct_keys

    first = [
        {"part_number": "150CX18", "description": "Hinge", "division": "08 71 00"},
        {"part_number": "B-2888", "description": "Dispenser", "division": "10 28 00"},
    ]
    reordered = [first[1], first[0]]

    assert set(_distinct_keys(first, _content_key)) == set(
        _distinct_keys(reordered, _content_key)
    )


def test_an_explicit_line_id_wins() -> None:
    from api.services.sync import _content_key

    assert _content_key({"line_id": "L-7", "part_number": "X"}) == "L-7"


# ── pricing: one bad line must not take the screen down ─────────────────────


def test_a_negative_cost_reports_unpriced_instead_of_raising() -> None:
    """`_recompute` walks every line on the bid.

    A single stored -45 used to raise out of the loop and 400 the quote and
    proposal screens, leaving no UI to correct it from.
    """
    from api.services import pricing

    priced = pricing.price_line(cost=-45.0, margin=0.27, qty=1, division="08 71 00")

    assert priced["priced"] is False
    assert priced["sell"] is None and priced["extended"] is None
    assert "negative" in priced["error"]


def test_an_ordinary_line_still_prices() -> None:
    from api.services import pricing

    priced = pricing.price_line(cost=74.33, margin=0.27, qty=3, division="08 71 00")
    assert priced["priced"] is True
    assert priced["sell"] == 101.82
    assert priced["extended"] == 305.46


def test_quote_line_schema_rejects_a_negative_cost() -> None:
    from pydantic import ValidationError

    from api.schemas.quote import QuoteLineUpdate

    with pytest.raises(ValidationError):
        QuoteLineUpdate(cost=-45)
    with pytest.raises(ValidationError):
        QuoteLineUpdate(qty=-1)
    assert QuoteLineUpdate(cost=45).cost == 45


def test_a_bad_cost_from_a_pipeline_run_is_flagged_not_stored() -> None:
    """The schema bounds what an estimator types; a run writes straight to Mongo."""
    from api.services.sync import _sane_cost

    cost, flags = _sane_cost({"cost": -45})
    assert cost is None and "negative cost" in flags[0]

    cost, flags = _sane_cost({"cost": "n/a"})
    assert cost is None and "unreadable cost" in flags[0]

    # An honest unpriced line stays unpriced, without inventing a flag.
    assert _sane_cost({"cost": None}) == (None, [])
    # And a good one is untouched.
    assert _sane_cost({"cost": 74.33, "flags": ["low_confidence"]}) == (74.33, ["low_confidence"])


# ── the exclusive-job policy and its index must agree ───────────────────────


def test_pricebook_ingest_is_not_an_exclusive_job() -> None:
    """It carries no project, so every one of them shares the key (null, type).

    Including it made the second price-book upload of the day silently return the
    first one's job instead of being queued.
    """
    from api.schemas.common import EXCLUSIVE_JOB_TYPES
    from api.services.jobs import EXCLUSIVE

    assert "ingest_pricebook" not in EXCLUSIVE_JOB_TYPES
    assert EXCLUSIVE == set(EXCLUSIVE_JOB_TYPES)


# ── the worker knows which failures are worth retrying ──────────────────────


def test_a_missing_cli_is_not_retried(monkeypatch) -> None:
    from cbc_core import claude_cli as runner

    monkeypatch.setattr(runner, "resolve_binary", lambda: None)
    result = runner.run_claude("hello")

    assert result.ok is False
    assert result.permanent is True, "a missing CLI is the same on the third attempt"


def test_an_authentication_failure_is_not_retried() -> None:
    """The CLI exits 0 on an auth failure, so only the message identifies it."""
    from cbc_core import claude_cli as runner

    result = runner._interpret("Invalid API key", "", 0, timeout=90, redact_values=None)

    assert result.ok is False
    assert result.permanent is True


def test_an_ordinary_failure_is_still_retried() -> None:
    from cbc_core import claude_cli as runner

    result = runner._interpret("", "transient network blip", 1, timeout=90, redact_values=None)

    assert result.ok is False
    assert result.permanent is False


# ── the file-safety hook sees Write and Edit, not only Bash ─────────────────


def _run_guard(payload: dict, project_root: str | None = None) -> subprocess.CompletedProcess:
    """Run the hook the way Claude Code runs it, with CLAUDE_PROJECT_DIR set.

    The guard protects *this project's* reference data and guardrails, resolved
    against that variable. It used to match any path segment called ".claude" or
    "pricebooks", which meant it also blocked writes to the user's own ~/.claude on
    the host - files that have nothing to do with this repository.
    """
    env = dict(os.environ, CLAUDE_PROJECT_DIR=project_root or str(ROOT))
    return subprocess.run(
        [sys.executable, str(ROOT / ".claude" / "hooks" / "pre_delete_guard.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.mark.parametrize(
    "path",
    [
        "pricebooks/hager_price_book_18.pdf",
        "reference-library/margins/margin_framework.json",
        ".claude/hooks/pre_send_quote.py",
        ".claude/settings.json",
    ],
)
def test_write_to_protected_data_is_blocked(path: str) -> None:
    result = _run_guard({"tool_name": "Write", "tool_input": {"file_path": path}})
    assert result.returncode == 2, result.stdout
    assert "BLOCKED" in result.stderr


@pytest.mark.parametrize(
    "path", ["/app/pricebooks/index.json", "/app/.claude/settings.json"]
)
def test_the_container_layout_is_protected_too(path: str) -> None:
    """Same rule, resolved against the container's project root."""
    result = _run_guard({"tool_name": "Write", "tool_input": {"file_path": path}}, "/app")
    assert result.returncode == 2, result.stdout


@pytest.mark.parametrize(
    "path", ["/home/cbc/.claude/settings.json", "/tmp/pricebooks/scratch.pdf"]
)
def test_a_directory_of_the_same_name_elsewhere_is_not_this_project(path: str) -> None:
    """The rule is about this repository, not about a word.

    Matching a bare path segment blocked the user's own ~/.claude - their settings,
    their notes - which is not what the file-safety rule protects.
    """
    result = _run_guard({"tool_name": "Write", "tool_input": {"file_path": path}}, "/app")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "path",
    [
        "projects/dutch_bros/extracted/door_schedule.json",
        "projects/dutch_bros/priced/line_items.json",
        "/app/projects/x/review/review_flags.json",
        # Names the directory without being in it.
        "projects/pricebooks_notes/summary.md",
    ],
)
def test_writing_inside_a_project_is_allowed(path: str) -> None:
    result = _run_guard({"tool_name": "Write", "tool_input": {"file_path": path}})
    assert result.returncode == 0, result.stderr


def test_bash_deletion_guard_still_applies() -> None:
    protected = "reference-library/margins"
    result = _run_guard(
        {"tool_name": "Bash", "tool_input": {"command": f"rm -rf {protected}"}}
    )
    assert result.returncode == 2


def test_plain_rm_on_claude_hooks_is_blocked() -> None:
    result = _run_guard(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "rm .claude/hooks/pre_delete_guard.py"},
        }
    )
    assert result.returncode == 2, result.stderr


def test_mcp_argument_targeting_pricebooks_is_blocked() -> None:
    result = _run_guard(
        {
            "tool_name": "mcp__artifact-storage__save_artifact",
            "tool_input": {
                "project": "demo",
                "path": "pricebooks/hager.pdf",
                "content": "{}",
            },
        }
    )
    assert result.returncode == 2, result.stderr


def test_mcp_p21_write_tool_name_is_blocked() -> None:
    result = _run_guard(
        {
            "tool_name": "mcp__p21-connector__update_item",
            "tool_input": {"part_number": "3500"},
        }
    )
    assert result.returncode == 2, result.stderr
    assert "NFR-5" in result.stderr
