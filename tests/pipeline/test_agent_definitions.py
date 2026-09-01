"""An agent's frontmatter and its body have to agree about what it can do.

`quality-reviewer` was told - by the build_proposal prompt and by its own Output
section - to run `scripts/render_review_summary.py`. Its tools were
`Read, Glob, Grep, Write`. Every proposal run therefore reached a step it had no
tool to take, and the only way to notice was to read two files side by side.

These read them side by side.
"""
from __future__ import annotations

import re

import pytest

from cbc.core import toolsets
from tests.shared import ROOT

AGENT_DIR = ROOT / ".claude" / "agents"
AGENTS = sorted(AGENT_DIR.glob("*.md"))
assert AGENTS, "no agent definitions found"


def _frontmatter_tools(text: str) -> list[str]:
    match = re.search(r"^tools:\s*(.+)$", text, re.MULTILINE)
    return [t.strip() for t in match.group(1).split(",")] if match else []


def _body(text: str) -> str:
    parts = text.split("---", 2)
    return parts[2] if len(parts) > 2 else text


@pytest.mark.parametrize("path", AGENTS, ids=lambda p: p.stem)
def test_an_agent_told_to_run_a_script_can_run_one(path) -> None:
    text = path.read_text(encoding="utf-8")
    runs_a_script = re.search(r"`?python[ \w./-]*\.py", _body(text))
    if not runs_a_script:
        pytest.skip("no script invocation in this agent")
    assert "Bash" in _frontmatter_tools(text), (
        f"{path.stem} is told to run {runs_a_script.group(0)!r} without Bash"
    )


@pytest.mark.parametrize("path", AGENTS, ids=lambda p: p.stem)
def test_every_mcp_tool_belongs_to_a_server_that_exists(path) -> None:
    text = path.read_text(encoding="utf-8")
    for tool in _frontmatter_tools(text):
        if not tool.startswith("mcp__"):
            continue
        server = tool.split("__")[1]
        assert server in toolsets.SERVERS, f"{path.stem} lists tool from {server!r}"


def test_the_delegation_rule_names_agents_that_exist() -> None:
    """The orchestrator picks `subagent_type` from this list.

    A name here that has no file is a delegation that fails at the call, several
    minutes into a run, with the phase's output never written.
    """
    from apps.worker import prompts

    listed = re.search(
        r"subagent_type: one of (.+?)\n\s*prompt:",
        prompts.DELEGATION_RULE,
        re.DOTALL,
    )
    assert listed, "the delegation rule no longer lists subagent types"
    names = {n.strip().rstrip(",") for n in listed.group(1).replace("\n", " ").split(",")}
    names = {n for n in names if n}

    on_disk = {p.stem for p in AGENTS}
    assert not names - on_disk, f"delegated to agents that do not exist: {names - on_disk}"


def test_no_agent_claims_a_server_the_deleted_alias_used_to_serve() -> None:
    """`pricebook` was an alias over `catalog`; both the agent body and the ingest
    prompt still sent runs to it long after it stopped existing."""
    for path in AGENTS:
        body = path.read_text(encoding="utf-8")
        assert "`pricebook` MCP" not in body, path.stem
