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

# Which job type each agent's phase corresponds to, so the headless path and the
# Ops-Hub worker scope the same phase the same way. Unknown agents fail rather
# than falling back to "everything" - a silent full surface is the bug this
# mapping exists to prevent.
job_type_for() {
  case "$1" in
    intake-coordinator|spec-scope-analyst|takeoff-engineer|frp-specialist)
      echo "extract_bid_set" ;;
    product-matcher|pricing-engineer)
      echo "match_and_price" ;;
    quote-builder|quality-reviewer|delivery-agent)
      echo "build_proposal" ;;
    pricebook-ingestor)
      echo "ingest_pricebook" ;;
    *)
      echo "No job type mapped for agent '$1' - add it to job_type_for" >&2
      return 1 ;;
  esac
}

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

  # The tool surface comes from cbc/core/toolsets.py, which is what the Ops-Hub
  # worker scopes each job with. This script used to pass no --mcp-config at
  # all, so a headless take-off got every server in .mcp.json plus WebSearch and
  # WebFetch - a wider surface than the same phase gets through the web app, and
  # the opposite of what an unattended pass over a customer's drawings wants.
  local job_type
  job_type="$(job_type_for "${agent}")" || return 1
  local scope
  if ! mapfile -t scope < <(PYTHONPATH="${ROOT}:${ROOT}/src"         python -m cbc.core.toolsets "${job_type}"); then
    echo "Could not read the tool scope for ${job_type}" >&2
    return 1
  fi

  # The constraints come from worker/prompts.py, which is what the Ops-Hub worker
  # runs with. This script used to restate them by hand, and the copy had fallen
  # behind: no manual cut-off, no P21 rule, no audit-trail line, and no
  # requirement that an extracted record carry a bbox. Same rules, one source.
  # CBC_SOLO=1 for a provider that cannot call the Agent tool. Without it this
  # script told every provider to delegate, so a local model was instructed to
  # use a tool it does not have and spent its turns circling - the same failure
  # the worker fixed by asking the provider first.
  local prompt_args=("${project_dir}")
  local how
  if [[ -n "${CBC_SOLO:-}" ]]; then
    prompt_args=(--solo "${project_dir}")
    how="Do this work yourself - the Agent tool is not available on this provider.
Read \`.claude/agents/${agent}.md\` and follow it: it holds the required output
fields, the tool order and the traps for this phase."
  else
    how="Delegate to the \`${agent}\` subagent with the Agent tool. Every Agent call
requires description, subagent_type, and prompt - calls missing description fail."
  fi

  local preamble
  if ! preamble="$(PYTHONPATH="${ROOT}:${ROOT}/src" python -m apps.worker.prompts "${prompt_args[@]}")"; then
    echo "Could not read the constraint preamble from worker/prompts.py" >&2
    return 1
  fi
  "${CLAUDE_BIN}" --print "${scope[@]}" --dangerously-skip-permissions "$(cat <<EOF
You are the CBC Estimating Copilot running ${label} for project ${project}.

${how}

Working directory for all inputs and outputs: ${project_dir}/
Bid-set PDFs: ${project_dir}/uploads/raw/

${instructions}

${preamble}
EOF
)"
}
