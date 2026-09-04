# Headless Setup

How to run the copilot unattended, and what keeps it safe when nobody is watching.

## Requirements

| Requirement | Notes |
|---|---|
| Python 3.11+ | 3.14 on the current machine |
| Claude Code CLI on `PATH` | override with `CLAUDE_BIN` |
| `mcp`, `pdfplumber`, `PyMuPDF`, `jinja2`, `openpyxl`, `pandas`, `Pillow` | `python -m pip install -e mcp-servers` |
| Bash | Git Bash on Windows; the scripts are POSIX sh |
| `poppler-utils` (`pdftoppm`) | Claude Code's Read tool on PDFs; in Docker this is in the image |

Optional: `pytesseract` plus the tesseract binary, for scanned bid sets. Without
it, OCR degrades with an explicit message rather than a silent empty string.

Not required: `jq` (hooks are Python), `rapidfuzz` (stdlib `difflib`),
`inotify-tools` (the watcher falls back to polling).

## Verify before the first unattended run

```bash
python mcp-servers/main.py --selftest
```

```bash
python scripts/validate_project.py --all
```

```bash
bash tests/test_guardrails/test_no_auto_send.sh && bash tests/test_guardrails/test_file_safety.sh
```

```bash
python -m pytest tests/ -q
```

All four must pass. The guardrail suites in particular - they are what makes
`--dangerously-skip-permissions` acceptable.

## Running a bid

```bash
bash scripts/init_project.sh dutch_bros_macarthur_2026 tests/fixtures/pdfs/1_Architectural.pdf
```

```bash
bash workflows/run_full_pipeline.sh dutch_bros_macarthur_2026
```

The pipeline runs pre-flight, then invokes:

```
claude --print --dangerously-skip-permissions "<orchestrator prompt>"
```

`--print` is non-interactive: one prompt in, output to stdout, exit.

### Why `--dangerously-skip-permissions` is used here

An unattended run cannot answer permission prompts. The safety does not come from
prompting - it comes from the hooks, which fire regardless of permission mode:

- `pre_send_quote.py` blocks every send path with exit code 2
- `pre_delete_guard.py` blocks deletes outside `projects/` and any delete touching
  reference data
- `log_audit_trail.py` records every tool call

Plus the deny list in `.claude/settings.json`, which is a second, independent
layer.

## Watching for new bid sets

```bash
bash workflows/watch_uploads.sh --interval 30
```

Uses `inotifywait` when present, otherwise polls. Pre-existing files are seeded on
start so they do not all fire at once.

### Windows scheduled task

```bash
schtasks /create /tn "CBC Copilot Watcher" /tr "C:\\Program Files\\Git\\bin\\bash.exe -lc 'cd /c/path/to/cbc-copilot && bash workflows/watch_uploads.sh'" /sc onstart /ru SYSTEM
```

### Linux systemd unit

```ini
[Unit]
Description=CBC Estimating Copilot upload watcher
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/cbc-estimating-copilot
ExecStart=/usr/bin/bash workflows/watch_uploads.sh
Restart=on-failure
RestartSec=10
User=cbc
Environment=CLAUDE_BIN=/usr/local/bin/claude

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now cbc-copilot-watcher
```

### Cron

```bash
*/15 * * * * cd /opt/cbc-estimating-copilot && bash workflows/watch_uploads.sh --interval 1 >> /var/log/cbc-copilot.log 2>&1
```

A weekly staleness check is worth having, given NFR-10 is still open:

```bash
0 8 * * 1 cd /opt/cbc-estimating-copilot && bash scripts/refresh_pricebooks.sh >> /var/log/cbc-pricebooks.log 2>&1
```

## Environment variables

| Variable | Used by | Default | Notes |
|---|---|---|---|
| `CLAUDE_BIN` | workflows | `claude` | Path to the CLI |
| `PRICEBOOK_DIR` | pricebook server | `pricebooks` | Point elsewhere to avoid duplicating books |
| `P21_BASE_URL` | p21-connector | unset | Unset means every lookup returns "manual entry required" |
| `P21_API_KEY` | p21-connector | unset | **Never commit this** |

Credentials belong in `.claude/settings.local.json`, which is gitignored.

## Running a single phase

```bash
bash workflows/phase3_takeoff.sh dutch_bros_macarthur_2026
```

Useful when re-running one step after a fix, without redoing the whole bid.

## What a successful run looks like

```
[2026-08-26T14:02:11] Pre-flight...
OK - 23 warning(s).
[2026-08-26T14:02:14] Starting Phase 0-6 for dutch_bros_macarthur_2026
...
[2026-08-26T14:09:47] Pipeline finished.
  Draft quotation: projects/dutch_bros_macarthur_2026/quotation.html
  Review summary:  projects/dutch_bros_macarthur_2026/review/review_summary.html
  Audit trail:     projects/dutch_bros_macarthur_2026/audit_trail.jsonl

Draft ready for estimator review. Nothing has been sent.
```

Pre-flight warnings about stale price books are expected today - 11 of 26 books are
past the 24-month review window. They are surfaced, not suppressed (NFR-10).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Project not found` | No scaffold | `bash scripts/init_project.sh <name>` |
| `No bid-set files in .../uploads/raw/` | Nothing to process | Copy the PDFs in |
| MCP server fails selftest | Missing dependency | `python -m pip install -e mcp-servers` |
| Extraction returns nothing | Scanned (image-only) PDF | Install `pytesseract` plus tesseract |
| Every price is MANUAL | Expected for Allegion, Zero and other non-top-10 lines | Not a bug - see `manual_cutoff.md` |
| Pipeline attempts to send | Should be impossible | Re-run the guardrail tests and stop using the pipeline until they pass |
