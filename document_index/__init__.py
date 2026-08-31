"""One-time LLM deep indexing for large, messy PDFs.

Each upload produces a versioned folder with index.json (routing), content.db
(full section content), schema_config.json, and manifest.json. Query-time tools
navigate the index and fetch only the relevant page range — never re-scan the
whole document.
"""
