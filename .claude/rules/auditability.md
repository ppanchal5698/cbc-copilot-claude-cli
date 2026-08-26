# Auditability (NFR-3)

**Every generated line must be traceable to a source drawing page and to a reference-library
or price-sheet version — including the vendor multiplier tier and its effective date.**

## Required provenance on every extracted record
- source_file — the PDF it came from
- source_page — 1-indexed page number (**mandatory**, no exceptions)
- extracted_at — ISO 8601 timestamp

## Required provenance on every priced line
- cost_source — one of P21_LAST_PO | LIST_X_MULTIPLIER | VENDOR_RFQ | DISTRIBUTOR_MANUAL | MANUAL
- cost_source_detail — PO date, or price-book file + page, or the distributor name
- multiplier_tier and multiplier_effective_date when Path 2 was used
- price_book_version — e.g. "Hager Price Book #18, effective 2026-02-02"
- priced_at — ISO 8601 timestamp

## Audit trail
Every tool call is appended to projects/{project}/audit_trail.jsonl by the
log_audit_trail.py PostToolUse hook. The trail is **append-only** and is version controlled.
Render it with scripts/export_audit_report.py

## Why
An estimator must be able to answer "where did this number come from?" months later, and
a stale price sheet must be visible as stale rather than silently wrong.

## Owner
CBC Estimating and IT.
