#!/usr/bin/env python3
"""PreToolUse guardrail: block destructive commands outside the project worktree.

Exit 2 = block the tool call. Exit 0 = allow.
Rule: .claude/rules/file-safety.md
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

PROTECTED = ("pricebooks/", "reference-library/", "pricebooks\\", "reference-library\\")

# Read-only reference data, plus the guardrails themselves. Until this hook read
# `file_path` it only ever inspected Bash commands, so a Write or an Edit walked
# straight into pricebooks/, reference-library/ or .claude/hooks/ - which is to
# say, a run could switch off the rules it was running under.
PROTECTED_DIRS = ("pricebooks", "reference-library", ".claude")

RM_RF = re.compile(r"\brm\b[^|;&]*-[a-zA-Z]*[rR][a-zA-Z]*f|\brm\b[^|;&]*-[a-zA-Z]*f[a-zA-Z]*[rR]")
RM_ANY = re.compile(r"\brm\b|\bdel\b|Remove-Item")
GIT_PUSH = re.compile(r"\bgit\s+push\b")


PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()


def _in_protected_dir(path: str) -> bool:
    """True when the path lands inside one of *this project's* read-only directories.

    Resolved and compared against the project root, rather than matched by name.
    The first version asked whether any segment of the path was called ".claude",
    which is true of ~/.claude on every machine - so it blocked writes to files
    with nothing to do with this project's guardrails, including the user's own
    settings and notes. The rule is about this repository, not about a word.
    """
    try:
        resolved = Path(path).resolve()
    except (OSError, ValueError):
        return False
    for directory in PROTECTED_DIRS:
        target = (PROJECT_ROOT / directory).resolve()
        if resolved == target or target in resolved.parents:
            return True
    return False


def block(reason: str) -> int:
    print(f"BLOCKED: {reason} (file-safety rule).", file=sys.stderr)
    return 2


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_input = payload.get("tool_input") or {}

    # Write / Edit / NotebookEdit name their target instead of carrying a command.
    target = str(
        tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    )
    if target and _in_protected_dir(target):
        return block(f"{target} is read-only during a run")

    command = str(tool_input.get("command") or "")
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
