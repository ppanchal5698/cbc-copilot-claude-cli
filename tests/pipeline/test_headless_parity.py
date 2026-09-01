"""The two ways to start a run must operate under the same rules and tools.

`_phase.sh` and `run_full_pipeline.sh` already share the preamble with the worker.
They did not share the tool scope: both spawned the CLI with no `--mcp-config`,
no `--strict-mcp-config` and no `--disallowed-tools`, so a headless take-off
carried every server in `.mcp.json` plus WebSearch and WebFetch - a wider surface
than the identical phase gets through the Ops-Hub, on the path with nobody
watching it.

`_phase.sh` also hardcoded "Delegate to the `${agent}` subagent", so a provider
that cannot call the Agent tool was told to use it anyway.
"""
from __future__ import annotations

import re

import pytest

from cbc.core import toolsets
from tests.shared import ROOT

WORKFLOWS = ROOT / "workflows"
PHASE_SH = (WORKFLOWS / "_phase.sh").read_text(encoding="utf-8")
PIPELINE_SH = (WORKFLOWS / "run_full_pipeline.sh").read_text(encoding="utf-8")
SPAWNING_SCRIPTS = {"_phase.sh": PHASE_SH, "run_full_pipeline.sh": PIPELINE_SH}


def _mapped_agents() -> dict[str, str]:
    """Parse the agent -> job type table out of the shell case statement."""
    block = re.search(r"job_type_for\(\) \{(.+?)\n\}", PHASE_SH, re.DOTALL)
    assert block, "job_type_for is gone from _phase.sh"
    mapping: dict[str, str] = {}
    for names, job_type in re.findall(
        r"^\s*([a-z|-]+)\)\s*\n?\s*echo \"([a-z_]+)\"", block.group(1), re.MULTILINE
    ):
        for name in names.split("|"):
            mapping[name] = job_type
    return mapping


@pytest.mark.parametrize("name", sorted(SPAWNING_SCRIPTS))
def test_a_headless_run_is_scoped_like_a_worker_run(name: str) -> None:
    body = SPAWNING_SCRIPTS[name]
    assert "cbc.core.toolsets" in body, f"{name} builds its own scope"
    spawn = re.search(r'"\$\{CLAUDE_BIN\}"[^\n]*', body)
    assert spawn, f"{name} no longer spawns the CLI"
    assert "SCOPE" in spawn.group(0) or "scope" in spawn.group(0), (
        f"{name} spawns the CLI without the tool scope: {spawn.group(0)}"
    )


def test_every_agent_has_a_job_type() -> None:
    """An unmapped agent used to mean the full tool surface. Now it is an error,
    but only if every agent is actually in the table."""
    mapping = _mapped_agents()
    on_disk = {p.stem for p in (ROOT / ".claude" / "agents").glob("*.md")}
    assert not on_disk - set(mapping), f"agents with no tool scope: {on_disk - set(mapping)}"


def test_every_mapped_job_type_is_a_real_profile() -> None:
    """A typo here would scope a phase to `PROFILES.get(...) or list(SERVERS)`,
    which is silently everything."""
    for agent, job_type in _mapped_agents().items():
        assert job_type in toolsets.PROFILES, f"{agent} -> unknown job type {job_type!r}"


def test_the_reading_phases_get_no_pricing_tools() -> None:
    """The scope the mapping actually produces, not just that it produces one."""
    import json

    mapping = _mapped_agents()
    servers = json.loads(toolsets.config_for(mapping["takeoff-engineer"]))["mcpServers"]
    assert "p21-connector" not in servers
    assert "calc-engine" not in servers
    assert "pdf-tools" in servers


@pytest.mark.parametrize("name", sorted(SPAWNING_SCRIPTS))
def test_a_solo_provider_is_not_told_to_delegate(name: str) -> None:
    body = SPAWNING_SCRIPTS[name]
    assert "CBC_SOLO" in body, f"{name} assumes every provider can delegate"
    assert "--solo" in body, f"{name} never asks prompts.py for the solo preamble"
