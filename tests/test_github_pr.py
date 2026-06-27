"""Tests for posting findings as inline PR review comments.

Network calls are mocked - these tests never make a real HTTP request.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

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

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        github_pr.post_review_comments(
            [FINDING], repo="acme/widgets", pull_number=42, commit_sha="abc123", token="tok"
        )
    assert exc_info.value.code == 500


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


def test_main_missing_findings_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/widgets")
    event_path = tmp_path / "event.json"
    event_path.write_text('{"pull_request": {"number": 1, "head": {"sha": "abc"}}}')
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    exit_code = github_pr.main([str(tmp_path / "missing.json")])

    assert exit_code == 1
    assert "not found" in capsys.readouterr().err


def test_main_malformed_findings_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/widgets")
    event_path = tmp_path / "event.json"
    event_path.write_text('{"pull_request": {"number": 1, "head": {"sha": "abc"}}}')
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    bad = tmp_path / "findings.json"
    bad.write_text("{not json")

    exit_code = github_pr.main([str(bad)])

    assert exit_code == 1
    assert "invalid JSON" in capsys.readouterr().err


def test_main_wrong_schema_findings(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/widgets")
    event_path = tmp_path / "event.json"
    event_path.write_text('{"pull_request": {"number": 1, "head": {"sha": "abc"}}}')
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    bad = tmp_path / "findings.json"
    bad.write_text('[{"unexpected_field": "value"}]')

    exit_code = github_pr.main([str(bad)])

    assert exit_code == 1
    assert "unexpected schema" in capsys.readouterr().err


def test_build_comment_payload_backtick_in_redacted_is_safe():
    finding_with_backtick = Finding(
        file="src/app.py",
        line=5,
        column=1,
        rule_id="generic_password",
        rule_name="Generic Password Assignment",
        severity="medium",
        redacted="pa****`lue",
    )
    payload = github_pr.build_comment_payload(finding_with_backtick, commit_sha="abc")
    body = payload["body"]
    # Ensure no unmatched backtick breaks a code span
    backtick_count = body.count("`")
    assert backtick_count % 2 == 0


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
