#!/usr/bin/env bash
# CBC Estimating Copilot - full Phase 0 to 6 pipeline, headless.
#
#   bash workflows/run_full_pipeline.sh <project_name>
#
# Halts at Phase 6 with a draft quotation. Nothing is sent (NFR-1).
set -euo pipefail

PROJECT_NAME="${1:?Usage: run_full_pipeline.sh <project_name>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="projects/${PROJECT_NAME}"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"

cd "${ROOT}"

if [[ ! -d "${PROJECT_DIR}" ]]; then
  echo "Project not found: ${PROJECT_DIR}" >&2
  echo "Create it first: bash scripts/init_project.sh ${PROJECT_NAME} <bid-set.pdf>" >&2
  exit 1
fi

if ! compgen -G "${PROJECT_DIR}/uploads/raw/*" > /dev/null; then
  echo "No bid-set files in ${PROJECT_DIR}/uploads/raw/ - nothing to process." >&2
  exit 1
fi

echo "[$(date -Iseconds)] Pre-flight..."
python scripts/validate_project.py --all || {
  echo "Pre-flight failed. Fix the errors above before running the pipeline." >&2
  exit 1
}

echo "[$(date -Iseconds)] Starting Phase 0-6 for ${PROJECT_NAME}"

# The orchestration prompt comes from worker/prompts.py, which is what the
# Ops-Hub worker runs. This script used to restate it - a third hand-copy of the
# rules, after _phase.sh was already moved onto the shared source. Same pipeline,
# whichever way it is started.
PROMPT="$(PYTHONPATH="${ROOT}:${ROOT}/src" python -m apps.worker.prompts --pipeline "${PROJECT_DIR}")" || {
  echo "Could not build the pipeline prompt from worker/prompts.py" >&2
  exit 1
}

"${CLAUDE_BIN}" --print --dangerously-skip-permissions "${PROMPT}"

echo
echo "[$(date -Iseconds)] Pipeline finished."
echo "  Draft quotation: ${PROJECT_DIR}/quotation.html"
echo "  Review summary:  ${PROJECT_DIR}/review/review_summary.html"
echo "  Audit trail:     ${PROJECT_DIR}/audit_trail.jsonl"
echo
echo "Draft ready for estimator review. Nothing has been sent."
