#!/usr/bin/env python3
"""PreToolUse guardrail: block destructive commands outside the project worktree.

Exit 2 = block the tool call. Exit 0 = allow.
Rule: .claude/rules/file-safety.md
"""
from __future__ import annotations

import json
import re
import sys

PROTECTED = ("pricebooks/", "reference-library/", "pricebooks\\", "reference-library\\")

RM_RF = re.compile(r"\brm\b[^|;&]*-[a-zA-Z]*[rR][a-zA-Z]*f|\brm\b[^|;&]*-[a-zA-Z]*f[a-zA-Z]*[rR]")
RM_ANY = re.compile(r"\brm\b|\bdel\b|Remove-Item")
GIT_PUSH = re.compile(r"\bgit\s+push\b")


def block(reason: str) -> int:
    print(f"BLOCKED: {reason} (file-safety rule).", file=sys.stderr)
    return 2


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    command = str((payload.get("tool_input") or {}).get("command") or "")
    if not command:
        return 0

    if GIT_PUSH.search(command):
        return block("git push is not permitted from the pipeline")

    if RM_ANY.search(command) and any(p in command for p in PROTECTED):
        return block("pricebooks/ and reference-library/ are read-only reference data")

    if RM_RF.search(command) and "projects/" not in command and "projects\\" not in command:
        return block("File deletion outside project scope is prohibited")

    return 0


if __name__ == "__main__":
    sys.exit(main())
