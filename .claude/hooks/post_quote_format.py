#!/usr/bin/env python3
"""PostToolUse: tidy quotation.html after it is written. Never blocks."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    path = str((payload.get("tool_input") or {}).get("file_path") or "")
    if not path.endswith("quotation.html"):
        return 0

    if shutil.which("prettier"):
        subprocess.run(["prettier", "--write", "--parser", "html", path], capture_output=True)
        return 0

    try:
        import pyhtmlbeautifier  # noqa: F401
    except ImportError:
        return 0
    subprocess.run([sys.executable, "-m", "pyhtmlbeautifier", path], capture_output=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
