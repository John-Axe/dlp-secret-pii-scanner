"""Posts findings as inline GitHub PR review comments using the REST API
and the built-in GITHUB_TOKEN - no external secrets required.

Run as `python -m dlp.github_pr <findings.json>` from a pull_request
workflow step. Findings JSON is whatever `dlp-scan --format json` produced.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from .scanner import Finding

API_VERSION = "2022-11-28"
USER_AGENT = "dlp-secret-pii-scanner"


def build_comment_payload(finding: Finding, commit_sha: str) -> dict:
    body = (
        f"**DLP scan: {finding.severity.upper()} — {finding.rule_name}** (`{finding.rule_id}`)\n\n"
        f"Possible secret/PII detected: `{finding.redacted}`.\n\n"
        "If this is a false positive, suppress it with a trailing `# dlp-ignore` comment "
        "or a `.dlpignore` pattern."
    )
    return {
        "body": body,
        "commit_id": commit_sha,
        "path": finding.file,
        "line": finding.line,
        "side": "RIGHT",
    }


def post_review_comments(
    findings: list[Finding],
    *,
    repo: str,
    pull_number: int,
    commit_sha: str,
    token: str,
) -> list[int]:
    """POSTs one inline review comment per finding. Returns the created
    comment IDs. A 422 (line isn't part of the diff, so GitHub can't anchor
    a comment there) is skipped rather than raised, since that's expected
    for findings outside the changed hunks.
    """
    posted: list[int] = []
    url = f"https://api.github.com/repos/{repo}/pulls/{pull_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }

    for finding in findings:
        payload = build_comment_payload(finding, commit_sha)
        request = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), method="POST", headers=headers
        )
        try:
            with urllib.request.urlopen(request) as response:
                body = json.loads(response.read())
                posted.append(body.get("id"))
        except urllib.error.HTTPError as exc:
            if exc.code == 422:
                continue
            raise
    return posted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Post DLP findings as inline PR review comments.")
    parser.add_argument(
        "findings_json", type=Path, help="Path to dlp-scan --format json output."
    )
    args = parser.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    event_path = os.environ.get("GITHUB_EVENT_PATH")

    if not (token and repo and event_path):
        print(
            "Missing GITHUB_TOKEN, GITHUB_REPOSITORY, or GITHUB_EVENT_PATH; skipping PR comments.",
            file=sys.stderr,
        )
        return 0

    with open(event_path, encoding="utf-8") as fh:
        event = json.load(fh)

    pull_request = event.get("pull_request")
    if not pull_request:
        print("Not a pull_request event; skipping PR comments.", file=sys.stderr)
        return 0

    pull_number = pull_request["number"]
    commit_sha = pull_request["head"]["sha"]

    with open(args.findings_json, encoding="utf-8") as fh:
        raw_findings = json.load(fh)
    findings = [Finding(**item) for item in raw_findings]

    if not findings:
        print("No findings to comment on.")
        return 0

    posted = post_review_comments(
        findings, repo=repo, pull_number=pull_number, commit_sha=commit_sha, token=token
    )
    print(f"Posted {len(posted)} inline review comment(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
