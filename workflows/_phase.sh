#!/usr/bin/env bash
# Shared headless invocation for the individual phase scripts.
#
#   source _phase.sh
#   run_phase <project> <agent> <phase-label> <instructions...>
#
# Each phaseN_*.sh is a thin wrapper over this. The wrappers exist because the
# architecture names them; the logic lives here once.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"

run_phase() {
  local project="${1:?project name required}"
  local agent="${2:?agent name required}"
  local label="${3:?phase label required}"
  shift 3
  local instructions="$*"

  local project_dir="projects/${project}"
  if [[ ! -d "${ROOT}/${project_dir}" ]]; then
    echo "Project not found: ${project_dir}" >&2
    echo "Create it first: bash scripts/init_project.sh ${project}" >&2
    return 1
  fi

  echo "[$(date -Iseconds)] ${label} - ${project} (agent: ${agent})"

  cd "${ROOT}"

  # The constraints come from worker/prompts.py, which is what the Ops-Hub worker
  # runs with. This script used to restate them by hand, and the copy had fallen
  # behind: no manual cut-off, no P21 rule, no audit-trail line, and no
  # requirement that an extracted record carry a bbox. Same rules, one source.
  local preamble
  if ! preamble="$(PYTHONPATH="${ROOT}:${ROOT}/src" python -m apps.worker.prompts "${project_dir}")"; then
    echo "Could not read the constraint preamble from worker/prompts.py" >&2
    return 1
  fi
  "${CLAUDE_BIN}" --print --dangerously-skip-permissions "$(cat <<EOF
You are the CBC Estimating Copilot running ${label} for project ${project}.

Delegate to the \`${agent}\` subagent with the Agent tool. Every Agent call
requires description, subagent_type, and prompt - calls missing description fail.

Working directory for all inputs and outputs: ${project_dir}/
Bid-set PDFs: ${project_dir}/uploads/raw/

${instructions}

${preamble}
EOF
)"
}
