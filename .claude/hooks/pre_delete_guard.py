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

PROTECTED_DIRS = ("pricebooks", "reference-library", ".claude")

# Bash `rm`/`del` checks match by substring because the command string is not always
# a resolvable path. Keep this aligned with PROTECTED_DIRS.
PROTECTED = (
    "pricebooks/",
    "reference-library/",
    "pricebooks\\",
    "reference-library\\",
    ".claude/",
    ".claude\\",
)

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


def _path_targets_protected(text: str) -> bool:
    """True when a path string points at read-only project data."""
    if not text:
        return False
    if _in_protected_dir(text):
        return True
    normalized = text.replace("\\", "/")
    if any(fragment in normalized for fragment in PROTECTED):
        return True
    for directory in PROTECTED_DIRS:
        if re.search(rf"(?:^|[/])({re.escape(directory)}(?:/|$))", normalized):
            return True
    return False


def _iter_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_iter_strings(item))
        return out
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_iter_strings(item))
        return out
    return []


_P21_FORBIDDEN = ("write", "update", "insert", "create", "delete", "post")


def block(reason: str) -> int:
    print(f"BLOCKED: {reason} (file-safety rule).", file=sys.stderr)
    return 2


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_input = payload.get("tool_input") or {}
    tool_name = str(payload.get("tool_name") or "")

    # Write / Edit / NotebookEdit name their target instead of carrying a command.
    target = str(
        tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    )
    if target and _in_protected_dir(target):
        return block(f"{target} is read-only during a run")

    if tool_name.startswith("mcp__p21-connector__"):
        lower = tool_name.lower()
        if any(word in lower for word in _P21_FORBIDDEN):
            return block("P21 write tools are forbidden (NFR-5)")

    for text in _iter_strings(tool_input):
        if _path_targets_protected(text):
            return block(f"{text} is read-only during a run")

    command = str(tool_input.get("command") or "")
    if not command:
        return 0

    if GIT_PUSH.search(command):
        return block("git push is not permitted from the pipeline")

    if RM_ANY.search(command):
        if any(p in command for p in PROTECTED):
            return block("pricebooks/, reference-library/, and .claude/ are read-only")
        # Plain `rm .claude/hooks/foo.py` (no trailing slash in PROTECTED) still
        # has to be caught — substring match on the directory name alone.
        normalized = command.replace("\\", "/")
        for directory in PROTECTED_DIRS:
            if re.search(rf"(?:^|[\s'\"])({re.escape(directory)}(?:/|$))", normalized):
                return block(f"{directory}/ is read-only during a run")

    if RM_RF.search(command) and "projects/" not in command and "projects\\" not in command:
        return block("File deletion outside project scope is prohibited")

    return 0


if __name__ == "__main__":
    sys.exit(main())
