#!/usr/bin/env bash
# Container start-up, before the API or the worker.
#
# Its whole job is declaring that /app is a trusted workspace. Claude Code
# ignores a project's permissions.allow entries until the trust dialog has been
# accepted, and an unattended container has nobody to accept it. Left unset,
# every MCP tool call is silently denied - which shows up as an extraction that
# found nothing, not as a permissions error, and costs an afternoon to diagnose.
#
# This runs on every start rather than at build time because the CLI rewrites
# ~/.claude.json the first time it runs, discarding a file it considers
# incomplete. Merging into whatever is there now is the version that sticks.
set -euo pipefail

python - <<'PY'
import json
from pathlib import Path

config = Path.home() / ".claude.json"
try:
    data = json.loads(config.read_text(encoding="utf-8")) if config.exists() else {}
except (json.JSONDecodeError, OSError):
    data = {}

project = data.setdefault("projects", {}).setdefault("/app", {})
if not project.get("hasTrustDialogAccepted"):
    project["hasTrustDialogAccepted"] = True
    config.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("[entrypoint] /app marked as a trusted workspace")
PY

exec "$@"
