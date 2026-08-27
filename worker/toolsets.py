"""Which tools each job type gets.

Every MCP server's schema sits in the context for the whole run, and every tool
in it is a candidate the model has to consider. A take-off pass that can see
`lookup_last_po` and `validate_margin` is paying for them twice: once in tokens,
and again in the chance it reaches for the wrong one.

So each job gets the servers its phase actually uses. `--strict-mcp-config` makes
the list exhaustive rather than additive, so nothing leaks in from `.mcp.json`.

This is a quality lever as much as a cost one. The cost is small and measurable
(~11 KB of schema down to ~4 KB on an extraction); the quality effect is that
the only tools on offer are the right ones.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

# Server name -> the script that serves it, mirroring .mcp.json.
SERVERS = {
    "pdf-tools": "./mcp-servers/pdf-tools/server.py",
    "pricebook": "./mcp-servers/pricebook/server.py",
    "calc-engine": "./mcp-servers/calc-engine/server.py",
    "artifact-storage": "./mcp-servers/artifact-storage/server.py",
    "p21-connector": "./mcp-servers/p21-connector/server.py",
    "catalog": "./mcp-servers/catalog/server.py",
}

# Reading drawings and writing what was found. No pricing tools exist at this
# stage, because nothing is priced at this stage.
_READING = ["pdf-tools", "artifact-storage"]

# Costing a confirmed schedule: the catalog and the price books for what things
# cost, calc-engine for the arithmetic, p21 for last-PO history.
_PRICING = ["catalog", "pricebook", "calc-engine", "p21-connector", "artifact-storage"]

PROFILES: dict[str, list[str]] = {
    "extract_bid_set": _READING,
    "rerun_extraction": _READING,
    "ingest_addendum": _READING,
    "match_and_price": _PRICING,
    # The proposal totals an already-priced quote; it reads no drawings.
    "build_proposal": ["calc-engine", "artifact-storage"],
    "ingest_pricebook": ["pricebook", "catalog", "artifact-storage"],
}

# Built-in tools no bid job has a use for. Bare names remove them from the
# context entirely rather than merely denying the call.
#
# A pass over a customer's drawings has no reason to reach the network, and
# saying so here is cheaper and clearer than trusting it not to.
DISALLOWED = ["WebSearch", "WebFetch", "NotebookEdit"]


def config_for(job_type: str, catalog_uri: str | None = None) -> str:
    """The `--mcp-config` payload for a job type, as a JSON string.

    The catalog server is handed its database credentials here rather than
    inheriting them, because the Claude Code process is deliberately not given
    any (see `api.services.provider.WITHHELD`). `catalog_uri` should be a
    read-only string; passing a writable one works and gives up the guarantee.
    """
    names = PROFILES.get(job_type) or list(SERVERS)
    servers: dict[str, Any] = {}
    for name in names:
        if name not in SERVERS:
            continue
        entry: dict[str, Any] = {"command": "python", "args": [SERVERS[name]]}
        if name == "catalog" and catalog_uri:
            entry["env"] = {"MONGODB_URI": catalog_uri}
        servers[name] = entry
    return json.dumps({"mcpServers": servers})


def flags_for(job_type: str, catalog_uri: str | None = None) -> list[str]:
    """CLI flags scoping a run to the tools its phase needs."""
    return [
        "--mcp-config",
        config_for(job_type, catalog_uri),
        "--strict-mcp-config",
        "--disallowed-tools",
        *DISALLOWED,
    ]
