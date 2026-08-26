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
  "${CLAUDE_BIN}" --print --dangerously-skip-permissions "$(cat <<EOF
You are the CBC Estimating Copilot running ${label} for project ${project}.

Delegate to the ${agent} sub-agent defined in .claude/agents/${agent}.md and
follow its instructions exactly.

Working directory for all inputs and outputs: ${project_dir}/
Bid-set PDFs: ${project_dir}/uploads/raw/

${instructions}

Constraints that override anything else:
- Respect every rule in .claude/rules/ and every guardrail in .claude/hooks/.
- Write only inside ${project_dir}/. Never write to pricebooks/ or reference-library/.
- Every extracted record carries source_page. Every priced line carries its cost source and date.
- Flag what you cannot determine. Never guess a fire rating, handing, finish, size or price.
- Do NOT send anything, by any means.
EOF
)"
}
