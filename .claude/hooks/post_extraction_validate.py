#!/usr/bin/env python3
"""PostToolUse: validate extraction output after it is written.

Never blocks - warnings go to stderr and the exit code stays 0 so the pipeline
continues and the estimator sees the flag in the review summary.
Rule: .claude/rules/accuracy-trust.md
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_RE = re.compile(r"projects/([^/]+)/extracted/")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    path = str((payload.get("tool_input") or {}).get("file_path") or "")
    match = PROJECT_RE.search(path.replace(chr(92), "/"))
    if not match:
        return 0

    project = match.group(1)
    validator = Path(__file__).resolve().parents[2] / "scripts" / "validate_project.py"
    if not validator.exists():
        return 0

    result = subprocess.run(
        [sys.executable, str(validator), "--check-extraction", project],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
