"""Tests for all output formats: table, json, sarif."""

from __future__ import annotations

import json

from dlp import report
from dlp.scanner import Finding

_F = Finding(
    file="src/app.py",
    line=10,
    column=5,
    rule_id="aws_access_key_id",
    rule_name="AWS Access Key ID",
    severity="high",
    redacted="AKIA****MPLE",
)


def test_to_table_empty_findings():
    assert report.to_table([]) == "No findings."


def test_to_table_contains_headers():
    out = report.to_table([_F])
    assert "SEVERITY" in out
    assert "RULE" in out
    assert "FILE" in out
    assert "LINE:COL" in out
    assert "PREVIEW" in out


def test_to_table_contains_finding_data():
    out = report.to_table([_F])
    assert "aws_access_key_id" in out
    assert "src/app.py" in out
    assert "10:5" in out
    assert "AKIA****MPLE" in out


def test_to_table_no_color_has_no_ansi_codes():
    out = report.to_table([_F], color=False)
    assert "\033[" not in out


def test_to_table_with_color_has_ansi_codes():
    out = report.to_table([_F], color=True)
    assert "\033[" in out


def test_to_table_finding_count_in_footer():
    out = report.to_table([_F, _F])
    assert "2 finding(s)" in out


def test_security_severity_score_returns_string():
    for sev in ("low", "medium", "high", "critical"):
        result = report._security_severity_score(sev)
        assert isinstance(result, str)
        float(result)  # must also be parseable as a number


def test_to_json_round_trips():
    out = json.loads(report.to_json([_F]))
    assert len(out) == 1
    assert out[0]["rule_id"] == "aws_access_key_id"
    assert out[0]["file"] == "src/app.py"


def test_to_json_empty():
    assert json.loads(report.to_json([])) == []
