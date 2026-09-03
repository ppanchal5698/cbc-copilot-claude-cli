#!/usr/bin/env python3
"""PostToolUse: validate extraction/pricing output after it is written.

Never blocks - warnings go to stderr and the exit code stays 0 so the pipeline
continues and the estimator sees the flag in the review summary.
Rule: .claude/rules/accuracy-trust.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _artifact_path import project_path_from_tool

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    return check(payload)


def check(payload: dict) -> int:
    tool_input = payload.get("tool_input") or {}
    resolved = project_path_from_tool(payload.get("tool_name"), tool_input)
    if not resolved:
        return 0

    project, rel_path = resolved
    try:
        from cbc.validation import check_extraction, check_pricing
    except ImportError:
        return 0

    if rel_path.startswith("extracted/"):
        problems, warnings = check_extraction(project)
    elif rel_path.startswith("priced/"):
        problems, warnings = check_pricing(project, require_hardware_sets=True)
    else:
        return 0

    for warning in warnings:
        print(f"WARN  {warning}", file=sys.stderr)
    for problem in problems:
        print(f"ERROR {problem}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
