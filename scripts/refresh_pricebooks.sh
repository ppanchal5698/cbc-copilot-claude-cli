#!/usr/bin/env bash
# Report the age of every price book and warn on stale sheets.
#
#   bash scripts/refresh_pricebooks.sh [--days N]
#
# Stale price sheets drive wrong quotes. NFR-10 (data stewardship) is still OPEN -
# no owner and no refresh cadence have been assigned - so this script is the
# interim mitigation, not the control.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DAYS=180
[[ "${1:-}" == "--days" ]] && DAYS="${2:?--days needs a number}"

python - "$ROOT" "$DAYS" <<'PY'
import json, sys
from datetime import date, datetime
from pathlib import Path

root, days = Path(sys.argv[1]), int(sys.argv[2])
index = root / "pricebooks" / "index.json"
if not index.exists():
    sys.exit("pricebooks/index.json not found")

books = json.loads(index.read_text(encoding="utf-8")).get("pricebooks", [])
stale, undated, fresh = [], [], []
for book in books:
    effective = book.get("effective_date")
    if not effective:
        undated.append(book)
        continue
    age = (date.today() - datetime.fromisoformat(effective).date()).days
    (stale if age > days else fresh).append((age, book))

print(f"{len(books)} price books indexed, threshold {days} days\n")
for age, book in sorted(stale, key=lambda item: item[0], reverse=True):
    print(f"  STALE   {age:>5}d  {book['file']}  (effective {book['effective_date']})")
for book in undated:
    print(f"  UNDATED        {book['file']}")
for age, book in sorted(fresh, key=lambda item: item[0], reverse=True):
    print(f"  ok      {age:>5}d  {book['file']}")

print(f"\n{len(stale)} stale, {len(undated)} undated, {len(fresh)} within threshold.")
if stale or undated:
    print("Owner and refresh cadence: UNASSIGNED (NFR-10 open). "
          "Manually entered prices always show 'price may be out of date - refresh'.")
PY
