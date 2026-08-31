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
import os
from pathlib import Path
from typing import Any
from cbc.core.paths import repo_root

REPO_ROOT = repo_root()

# Server name -> the script that serves it, mirroring .mcp.json.
SERVERS = {
    "pdf-tools": "./mcp-servers/pdf-tools/server.py",
    "calc-engine": "./mcp-servers/calc-engine/server.py",
    "artifact-storage": "./mcp-servers/artifact-storage/server.py",
    "p21-connector": "./mcp-servers/p21-connector/server.py",
    "catalog": "./mcp-servers/catalog/server.py",
    "document-index": "./mcp-servers/document-index/server.py",
}

# Reading drawings and writing what was found. No pricing tools exist at this
# stage, because nothing is priced at this stage.
_READING = ["pdf-tools", "artifact-storage"]

# Costing a confirmed schedule: the catalog for what things cost, calc-engine for
# the arithmetic, p21 for last-PO history.
#
# `catalog` used to appear here beside a `pricebook` server that was a pure alias
# over it, so a pricing pass carried search_product, list_vendors, lookup_pricing
# and get_multiplier twice under two names - the exact duplication this module
# exists to prevent.
_PRICING = ["catalog", "calc-engine", "p21-connector", "artifact-storage"]

# One run that spans every phase needs every server. Per-phase scoping is a real
# cost and quality lever when a job does one thing; here the same pass reads
# drawings, prices lines and writes artifacts, so narrowing it would only make a
# subagent reach for a tool it has not been given.
_EVERYTHING = list(SERVERS)

PROFILES: dict[str, list[str]] = {
    "run_full_pipeline": _EVERYTHING,
    "extract_bid_set": _READING,
    "rerun_extraction": _READING,
    "ingest_addendum": _READING,
    "match_and_price": _PRICING,
    # The proposal totals an already-priced quote; it reads no drawings.
    "build_proposal": ["calc-engine", "artifact-storage"],
    "ingest_pricebook": ["catalog", "artifact-storage"],
}

# Built-in tools no bid job has a use for. Bare names remove them from the
# context entirely rather than merely denying the call.
#
# A pass over a customer's drawings has no reason to reach the network, and
# saying so here is cheaper and clearer than trusting it not to.
DISALLOWED = ["WebSearch", "WebFetch", "NotebookEdit"]



def _readonly_uri() -> str | None:
    """The read-only connection string, derived rather than required in the env.

    `cbc.db` owns how it is built, but importing it here would point the shared
    floor at the domain package - so it is imported inside the call, where a
    missing database configuration degrades to "no catalog for this run" instead
    of breaking every job type that never needed one.
    """
    try:
        from cbc.db import readonly_uri

        return readonly_uri()
    except Exception:
        return os.environ.get("MONGODB_READONLY_URI")


def config_for(job_type: str, catalog_index_path: str | None = None) -> str:
    """The `--mcp-config` payload for a job type, as a JSON string.

    The catalog server reads the SQLite FTS index at ``CATALOG_INDEX_PATH``.
    The document-index server reads deep indexes at ``DOCUMENT_INDEX_ROOT``.
    """
    names = PROFILES.get(job_type) or list(SERVERS)
    servers: dict[str, Any] = {}
    index_path = catalog_index_path or os.environ.get("CATALOG_INDEX_PATH")
    document_root = os.environ.get("DOCUMENT_INDEX_ROOT")
    for name in names:
        if name not in SERVERS:
            continue
        entry: dict[str, Any] = {"command": "python", "args": [SERVERS[name]]}
        env: dict[str, str] = {}
        if name == "catalog":
            # The page index lives in MongoDB, and this is the one credential a
            # run is given for it: read-only, and no fallback to the writable
            # string. `provider.WITHHELD` keeps MONGODB_URI out of the subprocess
            # entirely, because pymongo is in the image and one Bash call with the
            # root URI would go straight past every read-only assertion the tools
            # make about themselves.
            readonly = _readonly_uri()
            if readonly:
                env["MONGODB_READONLY_URI"] = readonly
            if os.environ.get("MONGODB_DB"):
                env["MONGODB_DB"] = os.environ["MONGODB_DB"]
        if name == "document-index" and document_root:
            env["DOCUMENT_INDEX_ROOT"] = document_root
        if env:
            entry["env"] = env
        servers[name] = entry
    return json.dumps({"mcpServers": servers})


def flags_for(job_type: str, catalog_index_path: str | None = None) -> list[str]:
    """CLI flags scoping a run to the tools its phase needs."""
    return [
        "--mcp-config",
        config_for(job_type, catalog_index_path),
        "--strict-mcp-config",
        "--disallowed-tools",
        *DISALLOWED,
    ]
