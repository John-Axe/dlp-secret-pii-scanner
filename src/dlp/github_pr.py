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
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import severity
from .scanner import Finding

API_VERSION = "2022-11-28"
USER_AGENT = "dlp-secret-pii-scanner"

# A PR with hundreds of findings (e.g. someone commits a leaked-credentials
# dump - exactly the scenario this tool exists to catch) would otherwise fire
# that many sequential POSTs with no batching, which is both slow and a good
# way to trip GitHub's secondary rate limit. Capped by default; override with
# --max-comments. The highest-severity findings are kept when capping (see
# post_review_comments), not just the first N in file-scan order.
DEFAULT_MAX_COMMENTS = 25

# Bounded, not infinite: a real outage or a misconfigured token shouldn't
# retry forever and hang a CI job. 3 attempts with GitHub-directed backoff
# covers a transient secondary-rate-limit trip without masking a real,
# persistent problem behind an ever-growing wait.
MAX_RATE_LIMIT_RETRIES = 3


def build_comment_payload(finding: Finding, commit_sha: str) -> dict[str, Any]:
    safe_redacted = finding.redacted.replace("`", "*")
    body = (
        f"**DLP scan: {finding.severity.upper()} — {finding.rule_name}** (`{finding.rule_id}`)\n\n"
        f"Possible secret/PII detected: `{safe_redacted}`.\n\n"
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


def _is_rate_limited(exc: urllib.error.HTTPError) -> bool:
    """True for GitHub's secondary rate limit (429, or 403 carrying a
    Retry-After / exhausted X-RateLimit-Remaining header). A bare 403 with
    neither header is a real permissions error (e.g. a token missing
    pull-requests: write) and must NOT be retried - retrying it just turns
    an immediate, clear failure into a slow, confusing one.
    """
    if exc.code == 429:
        return True
    if exc.code == 403:
        return bool(exc.headers.get("Retry-After")) or exc.headers.get(
            "X-RateLimit-Remaining"
        ) == "0"
    return False


def _retry_after_seconds(exc: urllib.error.HTTPError, attempt: int) -> float:
    """GitHub tells you exactly how long to wait, when it can - prefer that
    over guessing. Falls back to capped exponential backoff only if neither
    header is present.
    """
    retry_after = exc.headers.get("Retry-After")
    if retry_after is not None:
        try:
            return float(retry_after)
        except ValueError:
            pass
    reset_at = exc.headers.get("X-RateLimit-Reset")
    if reset_at is not None:
        try:
            return max(0.0, float(reset_at) - time.time())
        except ValueError:
            pass
    return float(min(2**attempt, 60))


def _post_one_comment(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    *,
    max_retries: int,
    sleep: Callable[[float], None],
) -> int | None:
    """POSTs a single comment, retrying on a detected rate limit. Returns
    the created comment id, or None for a 422 (the finding's line isn't
    part of the diff, so GitHub can't anchor a comment there - expected for
    findings outside the changed hunks, not an error).
    """
    attempt = 0
    while True:
        request = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), method="POST", headers=headers
        )
        try:
            with urllib.request.urlopen(request) as response:
                body = json.loads(response.read())
                comment_id = body.get("id")
                return int(comment_id) if comment_id is not None else None
        except urllib.error.HTTPError as exc:
            if exc.code == 422:
                return None
            if _is_rate_limited(exc) and attempt < max_retries:
                sleep(_retry_after_seconds(exc, attempt))
                attempt += 1
                continue
            raise


def post_review_comments(
    findings: list[Finding],
    *,
    repo: str,
    pull_number: int,
    commit_sha: str,
    token: str,
    max_comments: int = DEFAULT_MAX_COMMENTS,
    max_retries: int = MAX_RATE_LIMIT_RETRIES,
    sleep: Callable[[float], None] = time.sleep,
) -> list[int]:
    """POSTs one inline review comment per finding, up to `max_comments`.

    If there are more findings than `max_comments`, the highest-severity
    ones are kept (see severity.rank) rather than just the first N in
    file-scan order, and a note is printed to stderr naming how many were
    left out - so capping is visible, not another silent drop.
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

    prioritized = sorted(findings, key=lambda f: severity.rank(f.severity), reverse=True)
    to_post = prioritized[:max_comments]
    omitted = len(prioritized) - len(to_post)

    for finding in to_post:
        payload = build_comment_payload(finding, commit_sha)
        comment_id = _post_one_comment(
            url, payload, headers, max_retries=max_retries, sleep=sleep
        )
        if comment_id is not None:
            posted.append(comment_id)

    if omitted > 0:
        print(
            f"dlp-scan: {omitted} additional finding(s) not posted as inline comments "
            f"(--max-comments={max_comments}); see the full results in this job's SARIF "
            "upload or table/JSON output instead.",
            file=sys.stderr,
        )

    return posted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Post DLP findings as inline PR review comments.")
    parser.add_argument(
        "findings_json", type=Path, help="Path to dlp-scan --format json output."
    )
    parser.add_argument(
        "--max-comments",
        type=int,
        default=DEFAULT_MAX_COMMENTS,  # dlp-ignore: identifier, not a secret
        help=f"Cap on inline comments posted, highest severity first "
        f"(default: {DEFAULT_MAX_COMMENTS}).",
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

    try:
        with open(args.findings_json, encoding="utf-8") as fh:
            raw_findings = json.load(fh)
    except FileNotFoundError:
        print(f"Findings file not found: {args.findings_json}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Findings file contains invalid JSON: {exc}", file=sys.stderr)
        return 1
    try:
        findings = [Finding(**item) for item in raw_findings]
    except TypeError as exc:
        print(f"Findings file has unexpected schema: {exc}", file=sys.stderr)
        return 1

    if not findings:
        print("No findings to comment on.")
        return 0

    posted = post_review_comments(
        findings,
        repo=repo,
        pull_number=pull_number,
        commit_sha=commit_sha,
        token=token,
        max_comments=args.max_comments,
    )
    print(f"Posted {len(posted)} inline review comment(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
