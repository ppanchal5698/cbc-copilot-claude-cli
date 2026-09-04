#!/usr/bin/env python3
"""Single PostToolUse process: validate, then format, then audit.

Always exits 0 — none of these checks may block the pipeline.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

import log_audit_trail  # noqa: E402
import post_extraction_validate  # noqa: E402
import post_quote_format  # noqa: E402


def check(payload: dict) -> int:
    # These were three separate processes, so one of them crashing could not take
    # the other two with it. Merged into one they can, and the one that must not
    # be lost is the audit trail: NFR-3 says every tool call is recorded. So it
    # runs first, and each step is isolated from the next.
    for step in (log_audit_trail, post_extraction_validate, post_quote_format):
        try:
            step.check(payload)
        except Exception as exc:  # noqa: BLE001 - a hook never blocks the pipeline
            print(f"hook {step.__name__} failed: {exc}", file=sys.stderr)
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    return check(payload)


if __name__ == "__main__":
    sys.exit(main())
