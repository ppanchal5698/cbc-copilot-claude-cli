#!/usr/bin/env python3
"""Development orchestrator for the five CBC MCP servers.

    python mcp-servers/main.py --selftest   # verify every server imports and lists its tools
    python mcp-servers/main.py              # start all five on stdio (local smoke testing)

In production Claude Code starts each server itself from .claude/settings.json.
Running them here is only useful for checking they come up at all.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVERS = [
    "pdf-tools",
    "pricebook",
    "calc-engine",
    "artifact-storage",
    "p21-connector",
    "catalog",
]
DEMOS = ["calc-engine", "artifact-storage", "p21-connector", "catalog"]


def selftest() -> int:
    failures = []
    for name in SERVERS:
        result = subprocess.run(
            [sys.executable, str(HERE / name / "server.py"), "--selftest"],
            capture_output=True,
            text=True,
        )
        print((result.stdout or result.stderr).strip())
        if result.returncode != 0:
            failures.append(name)

    for name in DEMOS:
        result = subprocess.run(
            [sys.executable, str(HERE / name / "server.py"), "--demo"],
            capture_output=True,
            text=True,
        )
        print((result.stdout or result.stderr).strip())
        if result.returncode != 0:
            failures.append(f"{name} (demo)")

    if failures:
        print(f"\nFAILED: {failures}")
        return 1
    print(f"\nAll {len(SERVERS)} MCP servers OK.")
    return 0


def run_all() -> int:
    processes = []
    for name in SERVERS:
        print(f"starting {name}...")
        processes.append(subprocess.Popen([sys.executable, str(HERE / name / "server.py")]))
    print("All servers running on stdio. Ctrl-C to stop.")
    try:
        for process in processes:
            process.wait()
    except KeyboardInterrupt:
        for process in processes:
            process.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else run_all())
