"""CLI to rebuild deep indexes from pricebooks or project PDFs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cbc.config import settings
from cbc.core.llm import LLMClient
from cbc.documents import storage
from cbc.documents.pipeline import index_document


def main() -> None:
    parser = argparse.ArgumentParser(description="Deep-index a PDF into document_index/")
    parser.add_argument("--client", required=True, help="client_id / vendor / project slug")
    parser.add_argument("--type", required=True, help="document_type e.g. multiplier_sheet, plan")
    parser.add_argument("--file", required=True, help="path to PDF relative to repo or absolute")
    parser.add_argument("--effective", default=None, help="effective date YYYY-MM-DD")
    parser.add_argument("--no-llm", action="store_true", help="use heuristic extraction only")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_absolute():
        path = (settings.repo_root / path).resolve()

    document_id = storage.allocate_document_id()
    llm = None if args.no_llm else LLMClient.from_env()
    report = index_document(
        path,
        document_id=document_id,
        client_id=args.client,
        document_type=args.type,
        effective_date=storage.normalise_effective(args.effective),
        llm=llm,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
