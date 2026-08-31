#!/usr/bin/env python3
"""Post Aug 24–28 worklogs to HMP-3 via Jira REST API (bypasses MCP write block).

Usage:
  set JIRA_EMAIL=you@dashtech.com
  set JIRA_API_TOKEN=your-token-from-id.atlassian.com
  python scripts/post_hmp3_worklogs_aug24_28.py

Dry run (no POST):
  python scripts/post_hmp3_worklogs_aug24_28.py --dry-run
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

JIRA_BASE = "https://dashtech.atlassian.net"
ISSUE_KEY = "HMP-3"

WORKLOGS = [
    ("2026-08-24T12:23:00.000+0530", "3h 35m", "Projects page replacing bid board: create/view/update/delete projects and attach bid PDFs through full lifecycle."),
    ("2026-08-24T16:11:00.000+0530", "1h 55m", "React hydration mismatch on new-estimate form; stabilised client/server render for date and dropdown fields."),
    ("2026-08-24T18:21:00.000+0530", "2h 44m", "AWS IAM consolidated cbc-copilot policy; verified CLI access; paused and removed cloud services for cost control."),
    ("2026-08-25T12:08:00.000+0530", "2h 15m", "CatalogItem schema expanded for price-book page, division, and net-cost fields; migration with full catalog truncate/reload."),
    ("2026-08-25T14:47:00.000+0530", "4h 50m", "Regenerated Hager Div 08/09/10 seed from final price books; reinserted entire catalog after model drop."),
    ("2026-08-25T19:42:00.000+0530", "1h 13m", "pgAdmin added to local compose; fixed localhost:5050 connectivity for Postgres inspection."),
    ("2026-08-26T12:31:00.000+0530", "3h 20m", "Initialised git repo and pushed full CBC Estimating Copilot codebase to GitHub (267 files, secrets excluded via .gitignore)."),
    ("2026-08-26T16:18:00.000+0530", "4h 51m", "OpsHub Next.js web app: sign-in, dashboard, bid board, intake/extraction/quote/proposal stages, API proxy layer."),
    ("2026-08-27T12:14:00.000+0530", "2h 5m", "Docker compose stack for api/worker/web/mongo; non-root worker entrypoint and trusted-workspace marking for Claude CLI."),
    ("2026-08-27T14:34:00.000+0530", "3h 40m", "Provider settings screen and env/DB resolution for which Claude Code instance runs pipeline jobs."),
    ("2026-08-27T18:27:00.000+0530", "2h 34m", "Live terminal drawer: SSE stream of worker Claude runs with job status sync back to MongoDB."),
    ("2026-08-28T12:19:00.000+0530", "5h 5m", "End-to-end smoke test of docker compose stack: bootstrap seed, job queue claim, catalog MCP wiring."),
    ("2026-08-28T17:38:00.000+0530", "3h 11m", "Compared CBC requirements workbook to implemented pricing/multiplier flow; noted gaps for Phase 1 vendor tiers."),
]


def _comment_adf(text: str) -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def _auth_header(email: str, token: str) -> str:
    raw = f"{email}:{token}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def post_worklog(email: str, token: str, started: str, time_spent: str, comment: str, dry_run: bool) -> None:
    url = f"{JIRA_BASE}/rest/api/3/issue/{ISSUE_KEY}/worklog"
    body = {"started": started, "timeSpent": time_spent, "comment": _comment_adf(comment)}
    if dry_run:
        print(f"[dry-run] {started} | {time_spent} | {comment[:60]}...")
        return
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": _auth_header(email, token),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            print(f"OK  id={data.get('id')}  {started}  {time_spent}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        print(f"FAIL {started} {time_spent}: HTTP {exc.code} {detail}", file=sys.stderr)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Post worklogs to {ISSUE_KEY}")
    parser.add_argument("--dry-run", action="store_true", help="Print payloads without posting")
    args = parser.parse_args()

    email = os.environ.get("JIRA_EMAIL", "").strip()
    token = os.environ.get("JIRA_API_TOKEN", "").strip()
    if not args.dry_run and (not email or not token):
        print(
            "Set JIRA_EMAIL and JIRA_API_TOKEN (create at https://id.atlassian.com/manage-profile/security/api-tokens)",
            file=sys.stderr,
        )
        return 1

    print(f"Posting {len(WORKLOGS)} worklogs to {ISSUE_KEY}...")
    for started, time_spent, comment in WORKLOGS:
        post_worklog(email, token, started, time_spent, comment, args.dry_run)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
