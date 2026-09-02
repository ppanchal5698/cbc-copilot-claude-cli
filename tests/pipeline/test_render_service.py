"""The proposal HTML comes from the scripts, whatever the pass decided to write.

`build_proposal` instructed `quote-builder` to run validate_and_render_quote.py
and `quality-reviewer` to run render_review_summary.py. Instructions are not
enforcement: an agent that hand-wrote the HTML produced a quotation that had
never been checked against the pricing rules, and `quality-reviewer` could not
have run its script in any case - Bash was not in its tool list.

The worker now runs both after the pass, so the markup and the arithmetic are the
same every time.
"""
from __future__ import annotations

import re

import pytest

from cbc.services import render
from tests.shared import ROOT

WORKER = (ROOT / "apps" / "worker" / "main.py").read_text(encoding="utf-8")


def _branch(job_type: str) -> str:
    """The body of one `if job["type"] == ...` branch in sync_results."""
    start = WORKER.index(f'if job["type"] == "{job_type}":')
    rest = WORKER[start:]
    nxt = re.search(r'\n    if job\["type"\]', rest[10:])
    return rest[: nxt.start() + 10] if nxt else rest


def test_the_render_helper_calls_both_scripts() -> None:
    """Rendering is centralized so job branches cannot skip either artifact."""
    start = WORKER.index("def _sync_blocking_render(")
    end = WORKER.index("\n\nasync def sync_results", start)
    body = WORKER[start:end]
    assert "render.render_quotation" in body
    assert "render.render_review_summary" in body


@pytest.mark.parametrize("job_type", ["build_proposal", "run_full_pipeline"])
def test_the_worker_renders_both_artifacts_itself(job_type: str) -> None:
    body = _branch(job_type)
    assert "_sync_blocking_render" in body, f"{job_type} trusts the pass for rendering"


def test_a_render_failure_is_reported_rather_than_raised() -> None:
    """A good review with a quote that does not validate is still worth keeping."""
    result = render.render_quotation("no_such_project_anywhere")
    assert not result.ok
    assert "line_items" in result.detail or "not written" in result.detail
    assert not result  # RenderResult is falsy when it failed


def test_the_scripts_it_calls_actually_exist() -> None:
    """A path typo here fails only at the end of a run that already cost minutes."""
    assert render.QUOTE_SCRIPT.exists(), render.QUOTE_SCRIPT
    assert render.REVIEW_SCRIPT.exists(), render.REVIEW_SCRIPT


def test_a_missing_script_is_a_clean_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(render, "QUOTE_SCRIPT", tmp_path / "gone.py")
    result = render.render_quotation("anything")
    assert not result.ok
    assert "missing" in result.detail
