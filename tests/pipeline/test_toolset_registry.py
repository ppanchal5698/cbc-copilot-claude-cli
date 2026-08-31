"""The toolset registry and .mcp.json must not drift apart.

`cbc_core/toolsets.py` hardcodes `SERVERS` (name -> script) to build the
`--mcp-config` for each job; `.mcp.json` is the inventory Claude Code reads. A
server named in one but not the other fails in a way that is easy to miss: named
in `SERVERS` but absent from `.mcp.json` and a scoped run cannot launch it;
present in `.mcp.json` but absent from `SERVERS` and it is silently never scoped
in. These pin the two together so the next server is added to both.
"""
from __future__ import annotations

import json

from cbc.core import toolsets
from tests.shared import ROOT


def _mcp_json_servers() -> dict[str, dict]:
    data = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    return data["mcpServers"]


def test_servers_match_the_mcp_json_registry() -> None:
    assert set(toolsets.SERVERS) == set(_mcp_json_servers())


def test_server_scripts_match_the_mcp_json_args() -> None:
    registry = _mcp_json_servers()
    for name, script in toolsets.SERVERS.items():
        assert registry[name]["args"] == [script], name
