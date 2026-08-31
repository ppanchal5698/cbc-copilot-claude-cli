#!/usr/bin/env python3
"""PreToolUse guardrail: block destructive commands outside the project worktree.

Exit 2 = block the tool call. Exit 0 = allow.
Rule: the file-safety rule in this project's rules directory.

The rule is about *writes*. Reading reference data is the pipeline's job - a
pricing pass exists to read price books - so nothing here may block a read.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

PROTECTED_DIRS = ("pricebooks", "reference-library", ".claude")

RM_RF = re.compile(r"\brm\b[^|;&]*-[a-zA-Z]*[rR][a-zA-Z]*f|\brm\b[^|;&]*-[a-zA-Z]*f[a-zA-Z]*[rR]")
GIT_PUSH = re.compile(r"\bgit\s+push\b")


PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()


def _in_protected_dir(path: str) -> bool:
    """True when the path lands inside one of *this project's* read-only directories.

    Resolved and compared against the project root, rather than matched by name.
    The first version asked whether any segment of the path was called ".claude",
    which is true of the user's own home-directory config on every machine - so it
    blocked writes to files with nothing to do with this project's guardrails,
    including their own settings and notes. The rule is about this repository, not
    about a word.

    This is the only authority for path-shaped input. A substring fallback was
    added alongside it once and silently overrode it, which reintroduced exactly
    that bug and additionally blocked read-only commands and any file whose text
    merely mentioned a protected directory. Do not add one back.
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


_P21_FORBIDDEN = ("write", "update", "insert", "create", "delete", "post")

# MCP tools that write. Their arguments name a destination, so a destination
# inside read-only reference data has to be refused - `save_artifact` pointed at
# a vendor sheet is the case this exists for.
#
# Matched on the verb rather than a list of tool names so a server added later is
# covered by default. Read tools are deliberately not checked: a pricing pass
# exists to read price books, and blocking that was the original bug.
_MCP_WRITE_VERBS = (
    "save", "write", "update", "insert", "upsert",
    "delete", "create", "put", "post", "set_", "remove",
)


def _is_mcp_write(tool_name: str) -> bool:
    lowered = tool_name.lower()
    return lowered.startswith("mcp__") and any(v in lowered for v in _MCP_WRITE_VERBS)


def _strings(value: object) -> list[str]:
    """Every string in a tool's arguments, however deeply nested."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in _strings(item)]
    return []


# Shell commands that write, and where in their arguments the destination sits.
# "last" is cp/mv-shaped: the final argument is the target, so `cp books/x /tmp/y`
# reads and is fine while `cp /tmp/y books/x` writes and is not. "any" is for
# commands where every path argument is a target.
_WRITE_LAST = ("cp", "mv", "install", "rsync")
# Deletion is a write. Listing it here means it is checked by resolving the target
# like everything else, rather than by substring-matching the command text - which
# fired on any command that merely contained the word and a path, a heredoc
# writing documentation about the rule included.
_WRITE_ANY = (
    "rm", "rmdir", "unlink", "del",
    "tee", "touch", "mkdir", "truncate", "chmod", "chown", "unzip", "tar",
)
_INPLACE = ("sed", "perl")


def _write_targets(command: str) -> list[str]:
    """Paths this command would write to. Empty for a command that only reads.

    ponytail: recognises write-shaped shell, not all of it. `bash -c`, a python
    one-liner, backticks, a variable holding the path, `find -exec` and `xargs`
    all still get through, and no amount of regex closes that - parsing arbitrary
    shell to decide intent is not a solvable problem. This catches accidents and
    the obvious cases, which is what a PreToolUse hook can honestly offer.

    The enforceable boundary is the filesystem: docker-compose already mounts the
    vendor sheets into the worker read-only (`:ro`), so in the container the kernel
    refuses the write regardless of how it is spelled. Treat this function as the
    local-development and defence-in-depth layer, not the guarantee.
    """
    # Each stage of a pipeline or chain is its own command: in `echo x | tee sheet`
    # the writer is `tee`, and looking only at the first word would miss it.
    return [
        target
        for segment in re.split(r"\|\||&&|[|;&\n()]", command)
        for target in _segment_write_targets(segment)
    ]


# Words that precede the real command without being it.
_WRAPPERS = ("sudo", "env", "nohup", "time", "command", "exec", "nice", "then", "do")


def _segment_write_targets(command: str) -> list[str]:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    if not tokens:
        return []

    targets: list[str] = []

    # Find the actual command word. `(cp a b` tokenises with the paren attached,
    # and `cp` != `(cp`, so the write went undetected - that is not a hypothetical:
    # it overwrote a vendor sheet during this work. Leading environment
    # assignments and wrapper words hide the command the same way.
    while tokens and (
        "=" in tokens[0].split("/")[0]
        or Path(tokens[0].strip("([{ ")).name in _WRAPPERS
    ):
        tokens = tokens[1:]
    if not tokens:
        return []
    tokens = [tokens[0].strip("([{ ")] + tokens[1:]

    # Redirection: the token after > or >>, or a >path written without a space.
    for index, token in enumerate(tokens):
        if token in (">", ">>") and index + 1 < len(tokens):
            targets.append(tokens[index + 1])
        elif token.startswith(">") and len(token.lstrip(">")) > 0:
            targets.append(token.lstrip(">"))

    name = Path(tokens[0]).name
    # Flags and redirection are not path arguments. `2>&1` trailing a command made
    # itself the "last argument" of a cp and hid the real destination behind it.
    arguments = [
        t for t in tokens[1:]
        if not t.startswith("-") and ">" not in t and "<" not in t
    ]

    if name in _WRITE_LAST and arguments:
        targets.append(arguments[-1])
    elif name in _WRITE_ANY:
        targets.extend(arguments)
    elif name in _INPLACE and any(t.startswith("-") and "i" in t for t in tokens[1:]):
        targets.extend(arguments)

    return targets


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

    # A writing MCP tool aimed at read-only reference data. Resolved against the
    # project root like every other path here, never substring-matched - the
    # substring version of this check is what blocked reads, unrelated homedirs,
    # and any file whose text merely mentioned a protected directory.
    if _is_mcp_write(tool_name):
        for value in _strings(tool_input):
            if _in_protected_dir(value):
                return block(f"{value} is read-only during a run")

    command = str(tool_input.get("command") or "")
    if not command:
        return 0

    if GIT_PUSH.search(command):
        return block("git push is not permitted from the pipeline")

    if RM_RF.search(command) and "projects/" not in command and "projects\\" not in command:
        return block("File deletion outside project scope is prohibited")

    # Writing into reference data by any other means. The rule says a run never
    # writes to these directories, but the check only ever ran inside an `rm`, so
    # `echo x > <a vendor sheet>` went straight through. Resolved per target, so a
    # command that merely reads from those directories is untouched.
    for target in _write_targets(command):
        if _in_protected_dir(target):
            return block(f"{target} is read-only during a run")

    return 0


if __name__ == "__main__":
    sys.exit(main())
