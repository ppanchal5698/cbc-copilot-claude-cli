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

"${CLAUDE_BIN}" --print --dangerously-skip-permissions "$(cat <<EOF
You are the CBC Estimating Copilot orchestrator.

Process the building-plan PDFs in ${PROJECT_DIR}/uploads/raw/ through the full
Phase 0-6 workflow documented in docs/cbc_process_flow.md.

Delegate each phase with the Agent tool (description + subagent_type + prompt
required on every call). Subagent types:

  Phase 0/1  intake-coordinator   -> extracted/scope_metadata.json
  Phase 2    spec-scope-analyst   -> extracted/scope_summary.json
  Phase 3    takeoff-engineer     -> extracted/door_schedule.json
  Phase 3b   frp-specialist       -> extracted/frp_takeoff.json (only if FRP is in scope)
  Phase 4    product-matcher      -> extracted/hardware_sets.json
  Phase 4    pricing-engineer     -> priced/line_items.json, priced/margin_applied.json
  Phase 4/6  quote-builder        -> quotation.html
  Phase 5    quality-reviewer     -> review/review_flags.json, review/review_summary.html
  Phase 6    delivery-agent       -> uploads/final/, review/quotation_email_draft.md

Start with find_sheets. Run parse_schedule.py --page N --openings --json for the
door schedule. Every opening needs source_page, bbox, page_size and confidence.

Non-negotiable:
- Respect every rule in .claude/rules/ and every guardrail in .claude/hooks/.
- Write all outputs inside ${PROJECT_DIR}/. Never write to pricebooks/ or reference-library/.
- Every extracted record carries source_page, page_size and bbox (NFR-3).
- Every priced line records its cost source, detail and date (NFR-3).
- Flag low confidence; never silently guess a rating, handing, finish, size or price (NFR-2).
- Beyond the top-10 stock items, take the MANUAL path. Do not price every option permutation.
- P21 is READ-ONLY (NFR-5).
- Log every action to ${PROJECT_DIR}/audit_trail.jsonl.

Do NOT send anything by any means. Stop at Phase 6 and report exactly:
"Draft ready for estimator review"
EOF
)"

echo
echo "[$(date -Iseconds)] Pipeline finished."
echo "  Draft quotation: ${PROJECT_DIR}/quotation.html"
echo "  Review summary:  ${PROJECT_DIR}/review/review_summary.html"
echo "  Audit trail:     ${PROJECT_DIR}/audit_trail.jsonl"
echo
echo "Draft ready for estimator review. Nothing has been sent."
