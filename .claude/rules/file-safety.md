# File Safety

## Writes
- Write **only** inside projects/{current_project}/ during a pipeline run.
- **Never write to pricebooks/ or reference-library/ during a run** — they are read-only
  reference data. Updating them is a separate, deliberate, human-initiated act.
- Raw uploads in projects/{project}/uploads/raw/ are **immutable**. Extraction output goes to
  uploads/processed/ or extracted/, never back over the original.

## Deletes
- **Never delete anything outside projects/{project}/.**
- Never delete anything in pricebooks/ or reference-library/, ever.
- rm -rf is blocked outside projects/ by .claude/hooks/pre_delete_guard.py (exit 2).
- git push is blocked by the same hook.

## Before overwriting
Read the target first. The artifact-storage MCP server keeps SHA-256 versioned copies of
everything it writes, so prefer save_artifact over a raw file write for anything an estimator
might need to compare against a previous run.

## Enforcement
- Hook: .claude/hooks/pre_delete_guard.py (PreToolUse, exit 2 blocks)
- Permission deny list in .claude/settings.json
