"""Tests for posting findings as inline PR review comments.

Network calls are mocked - these tests never make a real HTTP request.
"""

from __future__ import annotations

import io
import json
import urllib.error

from dlp import github_pr
from dlp.scanner import Finding

FINDING = Finding(
    file="src/app.py",
    line=12,
    column=5,
    rule_id="aws_access_key_id",
    rule_name="AWS Access Key ID",
    severity="high",
    redacted="AKIA************MPLE",
)


def test_build_comment_payload_has_required_fields():
    payload = github_pr.build_comment_payload(FINDING, commit_sha="abc123")

    assert payload["commit_id"] == "abc123"
    assert payload["path"] == "src/app.py"
    assert payload["line"] == 12
    assert payload["side"] == "RIGHT"
    assert "aws_access_key_id" in payload["body"]
    assert "AKIA" in payload["body"]


class _FakeResponse:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_post_review_comments_posts_one_per_finding(monkeypatch):
    calls = []

    def fake_urlopen(request):
        calls.append(request)
        return _FakeResponse({"id": 1000 + len(calls)})

    monkeypatch.setattr(github_pr.urllib.request, "urlopen", fake_urlopen)

    posted = github_pr.post_review_comments(
        [FINDING, FINDING], repo="acme/widgets", pull_number=42, commit_sha="abc123", token="tok"
    )

    assert posted == [1001, 1002]
    assert len(calls) == 2
    assert calls[0].full_url == "https://api.github.com/repos/acme/widgets/pulls/42/comments"
    assert calls[0].get_header("Authorization") == "Bearer tok"


def test_post_review_comments_skips_422_outside_diff(monkeypatch):
    def fake_urlopen(request):
        raise urllib.error.HTTPError(request.full_url, 422, "Unprocessable", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(github_pr.urllib.request, "urlopen", fake_urlopen)

    posted = github_pr.post_review_comments(
        [FINDING], repo="acme/widgets", pull_number=42, commit_sha="abc123", token="tok"
    )

    assert posted == []


def test_post_review_comments_reraises_other_http_errors(monkeypatch):
    def fake_urlopen(request):
        raise urllib.error.HTTPError(request.full_url, 500, "Server Error", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(github_pr.urllib.request, "urlopen", fake_urlopen)

    try:
        github_pr.post_review_comments(
            [FINDING], repo="acme/widgets", pull_number=42, commit_sha="abc123", token="tok"
        )
        assert False, "expected HTTPError to propagate"
    except urllib.error.HTTPError as exc:
        assert exc.code == 500


def test_main_skips_when_env_vars_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    findings_path = tmp_path / "findings.json"
    findings_path.write_text("[]")

    exit_code = github_pr.main([str(findings_path)])

    assert exit_code == 0


def test_main_skips_when_not_a_pull_request_event(tmp_path, monkeypatch):
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"push": {}}))
    findings_path = tmp_path / "findings.json"
    findings_path.write_text("[]")

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/widgets")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    exit_code = github_pr.main([str(findings_path)])

    assert exit_code == 0


def test_main_posts_comments_for_pull_request_event(tmp_path, monkeypatch):
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({"pull_request": {"number": 7, "head": {"sha": "deadbeef"}}})
    )
    findings_path = tmp_path / "findings.json"
    findings_path.write_text(json.dumps([FINDING.to_dict()]))

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/widgets")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    captured_kwargs = {}

    def fake_post(findings, **kwargs):
        captured_kwargs.update(kwargs)
        captured_kwargs["findings"] = findings
        return [1]

    monkeypatch.setattr(github_pr, "post_review_comments", fake_post)

    exit_code = github_pr.main([str(findings_path)])

    assert exit_code == 0
    assert captured_kwargs["repo"] == "acme/widgets"
    assert captured_kwargs["pull_number"] == 7
    assert captured_kwargs["commit_sha"] == "deadbeef"
    assert captured_kwargs["findings"][0].rule_id == "aws_access_key_id"
