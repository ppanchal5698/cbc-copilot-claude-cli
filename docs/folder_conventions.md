# Folder Conventions

This document records naming rules and intentional exceptions for the repository
layout. The runtime tree is summarized in [`architecture.md`](architecture.md).

## Directory naming

| Style | Examples | Rule |
|---|---|---|
| kebab-case | `mcp-servers/`, `reference-library/` | **Default for new directories** |
| single word | `api/`, `web/`, `worker/`, `docs/`, `scripts/` | Established service or role names |
| snake_case | `final_pricebooks/` | Legacy source tree — do not rename without updating ingest scripts |

Stable runtime paths (`projects/`, `pricebooks/`, MCP server folder names) are
hard-coded in skills, `.mcp.json`, Docker mounts, and `api/config.py`. Renaming
them requires a coordinated migration.

## Documentation files

All markdown files under `docs/` use **snake_case** filenames:

- `cbc_process_flow.md`
- `architecture.md`
- `development_description.md`
- `folder_conventions.md`

Bootstrap artifacts live under `docs/bootstrap/` (historical one-shot prompts).

## Test layout

```
tests/
├── conftest.py          # Shared pytest fixtures
├── shared.py            # ROOT, opshub_client(), FIXTURE_PDF
├── pipeline/            # MCP, extraction, guardrail tests
├── api/                 # Ops-Hub API tests (require MongoDB)
└── fixtures/
    ├── pdfs/            # Bid-set PDF fixtures (formerly building-plans/)
    ├── projects/        # Frozen JSON from past runs
    └── scratch/         # Ephemeral API test workspaces (gitignored)
```

Run everything: `python -m pytest tests/ -q`

## Project workspaces

Each bid slug under `projects/{slug}/` follows:

```
uploads/raw/          # Immutable bid PDFs (gitignored)
uploads/processed/    # Intermediate renders (gitignored)
uploads/final/        # Approved outputs (tracked when present)
extracted/            # Phase 2–3 JSON artifacts
priced/               # Phase 4 JSON artifacts
review/               # Phase 5–6 review artifacts
quotation.html        # Draft quotation at project root
audit_trail.jsonl     # Hook-written tool log (tracked for demo)
.runs/                # Job terminal recordings (gitignored)
.versions/            # Artifact-storage SHA history (gitignored)
```

Only the canonical demo project (`dutch_bros_macarthur_2026`) is committed with
curated artifacts. API tests use `tests/fixtures/scratch/` via `isolated_storage`.

## Data directories

| Path | Role |
|---|---|
| `final_pricebooks/` | Raw vendor uploads (UPPERCASE dirs, original filenames) |
| `pricebooks/` | Normalized runtime files consumed by MCP and Docker |
| `reference-library/` | Structured JSON — margins, multipliers, hardware sets |
| `storage/` | Reserved gitignored runtime slot (unused today) |

See [`pricebooks/README.md`](../pricebooks/README.md) for the source → runtime pipeline.

## What belongs at repo root

Configuration and entrypoints only: `CLAUDE.md`, `.mcp.json`, `Dockerfile`,
`docker-compose*.yml`, `requirements.txt`, `pytest.ini`, `README.md`.

Documentation, bootstrap prompts, and test fixtures belong under `docs/` and
`tests/fixtures/` respectively — not at the repository root.
