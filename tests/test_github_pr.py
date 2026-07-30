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


def _rate_limit_error(url: str, code: int, headers: dict | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "Rate limited", headers or {}, io.BytesIO(b"{}"))


def test_is_rate_limited_429_is_always_rate_limited():
    assert github_pr._is_rate_limited(_rate_limit_error("u", 429)) is True


def test_is_rate_limited_403_with_retry_after_is_rate_limited():
    exc = _rate_limit_error("u", 403, {"Retry-After": "30"})
    assert github_pr._is_rate_limited(exc) is True


def test_is_rate_limited_403_with_exhausted_primary_limit_is_rate_limited():
    exc = _rate_limit_error("u", 403, {"X-RateLimit-Remaining": "0"})
    assert github_pr._is_rate_limited(exc) is True


def test_is_rate_limited_bare_403_is_a_real_permission_error_not_retried():
    """A 403 with neither header is a token lacking pull-requests: write,
    or similar - retrying it would just turn an immediate, clear failure
    into a slow, confusing one."""
    exc = _rate_limit_error("u", 403, {})
    assert github_pr._is_rate_limited(exc) is False


def test_is_rate_limited_422_is_not_rate_limited():
    assert github_pr._is_rate_limited(_rate_limit_error("u", 422)) is False


def test_retry_after_seconds_prefers_retry_after_header():
    exc = _rate_limit_error("u", 429, {"Retry-After": "12"})
    assert github_pr._retry_after_seconds(exc, attempt=0) == 12.0


def test_retry_after_seconds_falls_back_to_rate_limit_reset(monkeypatch):
    monkeypatch.setattr(github_pr.time, "time", lambda: 1000.0)
    exc = _rate_limit_error("u", 429, {"X-RateLimit-Reset": "1030"})
    assert github_pr._retry_after_seconds(exc, attempt=0) == 30.0


def test_retry_after_seconds_ignores_malformed_retry_after_header():
    """A malformed header from a proxy/gateway shouldn't crash the retry
    logic - falls through to X-RateLimit-Reset, then to backoff."""
    exc = _rate_limit_error("u", 429, {"Retry-After": "not-a-number"})
    assert github_pr._retry_after_seconds(exc, attempt=0) == 1.0  # backoff fallback


def test_retry_after_seconds_ignores_malformed_rate_limit_reset_header(monkeypatch):
    exc = _rate_limit_error("u", 429, {"X-RateLimit-Reset": "not-a-number"})
    assert github_pr._retry_after_seconds(exc, attempt=2) == 4.0  # backoff fallback


def test_retry_after_seconds_falls_back_to_capped_exponential_backoff():
    exc = _rate_limit_error("u", 429, {})
    assert github_pr._retry_after_seconds(exc, attempt=0) == 1.0
    assert github_pr._retry_after_seconds(exc, attempt=3) == 8.0
    assert github_pr._retry_after_seconds(exc, attempt=10) == 60.0  # capped


def test_post_review_comments_retries_once_on_rate_limit_then_succeeds(monkeypatch):
    calls = []
    sleeps = []

    def fake_urlopen(request):
        calls.append(request)
        if len(calls) == 1:
            raise _rate_limit_error(request.full_url, 429, {"Retry-After": "5"})
        return _FakeResponse({"id": 42})

    monkeypatch.setattr(github_pr.urllib.request, "urlopen", fake_urlopen)

    posted = github_pr.post_review_comments(
        [FINDING],
        repo="acme/widgets",
        pull_number=1,
        commit_sha="abc",
        token="tok",
        sleep=sleeps.append,
    )

    assert posted == [42]
    assert len(calls) == 2  # one failed attempt, one retry that succeeded
    assert sleeps == [5.0]


def test_post_review_comments_gives_up_after_max_retries(monkeypatch):
    def fake_urlopen(request):
        raise _rate_limit_error(request.full_url, 429, {"Retry-After": "1"})

    monkeypatch.setattr(github_pr.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(urllib.error.HTTPError):
        github_pr.post_review_comments(
            [FINDING],
            repo="acme/widgets",
            pull_number=1,
            commit_sha="abc",
            token="tok",
            max_retries=2,
            sleep=lambda seconds: None,
        )


def test_post_review_comments_does_not_retry_bare_403(monkeypatch):
    slept = []

    def fake_urlopen(request):
        raise _rate_limit_error(request.full_url, 403, {})

    monkeypatch.setattr(github_pr.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        github_pr.post_review_comments(
            [FINDING],
            repo="acme/widgets",
            pull_number=1,
            commit_sha="abc",
            token="tok",
            sleep=slept.append,
        )

    assert exc_info.value.code == 403
    assert slept == []  # never treated as a retryable rate limit


def test_post_review_comments_caps_at_max_comments_keeping_highest_severity(monkeypatch):
    low = Finding(
        file="a.py", line=1, column=1, rule_id="email", rule_name="Email",
        severity="low", redacted="a***b",
    )
    critical = Finding(
        file="b.py", line=2, column=1, rule_id="private_key_block", rule_name="Private Key",
        severity="critical", redacted="c***d",
    )
    medium = Finding(
        file="c.py", line=3, column=1, rule_id="jwt", rule_name="JWT",
        severity="medium", redacted="e***f",
    )
    posted_paths = []

    def fake_urlopen(request):
        payload = json.loads(request.data)
        posted_paths.append(payload["path"])
        return _FakeResponse({"id": len(posted_paths)})

    monkeypatch.setattr(github_pr.urllib.request, "urlopen", fake_urlopen)

    posted = github_pr.post_review_comments(
        [low, critical, medium],
        repo="acme/widgets",
        pull_number=1,
        commit_sha="abc",
        token="tok",
        max_comments=2,
    )

    assert len(posted) == 2
    # Highest severity first: critical (b.py), then medium (c.py) - low (a.py) dropped.
    assert posted_paths == ["b.py", "c.py"]


def test_post_review_comments_reports_omitted_count_on_stderr_when_capped(monkeypatch, capsys):
    findings = [FINDING, FINDING, FINDING]

    def fake_urlopen(request):
        return _FakeResponse({"id": 1})

    monkeypatch.setattr(github_pr.urllib.request, "urlopen", fake_urlopen)

    github_pr.post_review_comments(
        findings, repo="acme/widgets", pull_number=1, commit_sha="abc", token="tok", max_comments=1
    )

    err = capsys.readouterr().err
    assert "2 additional finding(s)" in err
    assert "--max-comments=1" in err


def test_post_review_comments_no_stderr_note_when_not_capped(monkeypatch, capsys):
    def fake_urlopen(request):
        return _FakeResponse({"id": 1})

    monkeypatch.setattr(github_pr.urllib.request, "urlopen", fake_urlopen)

    github_pr.post_review_comments(
        [FINDING], repo="acme/widgets", pull_number=1, commit_sha="abc", token="tok"
    )

    assert capsys.readouterr().err == ""


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
    assert captured_kwargs["max_comments"] == github_pr.DEFAULT_MAX_COMMENTS


def test_main_respects_max_comments_flag(tmp_path, monkeypatch):
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"pull_request": {"number": 7, "head": {"sha": "deadbeef"}}}))
    findings_path = tmp_path / "findings.json"
    findings_path.write_text(json.dumps([FINDING.to_dict()]))

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/widgets")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    captured_kwargs = {}

    def fake_post(findings, **kwargs):
        captured_kwargs.update(kwargs)
        return [1]

    monkeypatch.setattr(github_pr, "post_review_comments", fake_post)

    exit_code = github_pr.main([str(findings_path), "--max-comments", "5"])

    assert exit_code == 0
    assert captured_kwargs["max_comments"] == 5
