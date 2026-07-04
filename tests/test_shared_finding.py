"""Tests for the shared-ecosystem finding schema adapter."""

from __future__ import annotations

import json

from dlp.scanner import Finding
from dlp.shared_finding import SOURCE, to_shared_finding, write_shared_findings_jsonl

_SECRET = Finding(
    file="src/app.py",
    line=10,
    column=5,
    rule_id="aws_access_key_id",
    rule_name="AWS Access Key ID",
    severity="high",
    redacted="AKIA****MPLE",
)

_PII = Finding(
    file="src/users.py",
    line=3,
    column=1,
    rule_id="email",
    rule_name="Email Address",
    severity="low",
    redacted="j***@example.com",
)

_REQUIRED_SCHEMA_FIELDS = {"id", "source", "timestamp", "severity", "category", "title", "description"}


def test_secret_finding_maps_to_secret_category_with_mitre_and_owasp():
    d = to_shared_finding(_SECRET)
    assert _REQUIRED_SCHEMA_FIELDS <= d.keys()
    assert d["source"] == SOURCE
    assert d["severity"] == "high"
    assert d["category"] == "secret"
    assert d["mitre_attack"] == ["T1552.001"]
    assert d["owasp"] == ["A02:2021"]
    assert d["resource"] == "src/app.py:10"
    assert d["raw"]["rule_id"] == "aws_access_key_id"
    assert d["raw"]["fingerprint"] == _SECRET.fingerprint


def test_pii_finding_maps_to_pii_category_with_no_mitre_or_owasp():
    d = to_shared_finding(_PII)
    assert d["category"] == "pii"
    assert d["mitre_attack"] == []
    assert d["owasp"] == []


def test_each_call_gets_a_unique_id():
    a = to_shared_finding(_SECRET)
    b = to_shared_finding(_SECRET)
    assert a["id"] != b["id"]


def test_write_shared_findings_jsonl_one_line_per_finding(tmp_path):
    out = tmp_path / "nested" / "findings.jsonl"
    write_shared_findings_jsonl([_SECRET, _PII], out)

    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first, second = (json.loads(line) for line in lines)
    assert first["category"] == "secret"
    assert second["category"] == "pii"


def test_write_shared_findings_jsonl_overwrites_not_appends(tmp_path):
    out = tmp_path / "findings.jsonl"
    write_shared_findings_jsonl([_SECRET], out)
    write_shared_findings_jsonl([_PII], out)

    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["category"] == "pii"
