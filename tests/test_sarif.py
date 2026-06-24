"""Tests for SARIF 2.1.0 output."""

from __future__ import annotations

import json
from pathlib import Path

from dlp import report
from dlp.scanner import scan_file


def test_sarif_is_valid_json_with_required_top_level_keys(tmp_path: Path):
    target = tmp_path / "creds.txt"
    target.write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")
    findings = scan_file(target)

    sarif = json.loads(report.to_sarif(findings))

    assert sarif["version"] == "2.1.0"
    assert "$schema" in sarif
    assert len(sarif["runs"]) == 1
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "dlp-secret-pii-scanner"


def test_sarif_rules_array_includes_every_detector_even_with_no_findings():
    sarif = json.loads(report.to_sarif([]))
    rule_ids = {r["id"] for r in sarif["runs"][0]["tool"]["driver"]["rules"]}

    assert "aws_access_key_id" in rule_ids
    assert "high_entropy_string" in rule_ids
    assert sarif["runs"][0]["results"] == []


def test_sarif_result_maps_file_line_column_and_rule(tmp_path: Path):
    target = tmp_path / "creds.txt"
    target.write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")
    findings = scan_file(target, display_path="creds.txt")

    sarif = json.loads(report.to_sarif(findings))
    result = sarif["runs"][0]["results"][0]

    assert result["ruleId"] == "aws_access_key_id"
    location = result["locations"][0]["physicalLocation"]
    assert location["artifactLocation"]["uri"] == "creds.txt"
    assert location["region"]["startLine"] == 1
    assert "partialFingerprints" in result


def test_sarif_severity_maps_to_sarif_level():
    assert report.SEVERITY_TO_SARIF_LEVEL["critical"] == "error"
    assert report.SEVERITY_TO_SARIF_LEVEL["high"] == "error"
    assert report.SEVERITY_TO_SARIF_LEVEL["medium"] == "warning"
    assert report.SEVERITY_TO_SARIF_LEVEL["low"] == "note"
