"""Tests for the file/tree scanner, ignore mechanism, and severity gating."""

from __future__ import annotations

from pathlib import Path

import pytest

from dlp import severity
from dlp.ignore import is_path_ignored, load_dlpignore
from dlp.scanner import scan_file, scan_paths


def test_scan_file_finds_planted_secret(tmp_path: Path):
    target = tmp_path / "creds.txt"
    target.write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")

    findings = scan_file(target)

    assert any(f.rule_id == "aws_access_key_id" for f in findings)


def test_scan_file_clean_file_has_no_findings(tmp_path: Path):
    target = tmp_path / "clean.txt"
    target.write_text("Just a normal line of text with nothing sensitive in it.\n")

    findings = scan_file(target)

    assert findings == []


def test_inline_dlp_ignore_suppresses_line(tmp_path: Path):
    target = tmp_path / "fixture.py"
    target.write_text(
        'FAKE_KEY = "AKIAIOSFODNN7EXAMPLE"  # dlp-ignore\n'
        'REAL_KEY = "AKIAIOSFODNN7EXAMPLE"\n'
    )

    findings = scan_file(target)

    assert len(findings) == 1
    assert findings[0].line == 2


def test_dlpignore_file_skips_matching_paths(tmp_path: Path):
    (tmp_path / ".dlpignore").write_text("vendor/*\n")
    vendor_dir = tmp_path / "vendor"
    vendor_dir.mkdir()
    (vendor_dir / "secret.txt").write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")
    (tmp_path / "app.py").write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")

    findings = scan_paths([tmp_path])

    files_with_findings = {f.file for f in findings}
    assert not any("vendor" in f for f in files_with_findings)
    assert any("app.py" in f for f in files_with_findings)


def test_load_dlpignore_skips_comments_and_blank_lines(tmp_path: Path):
    (tmp_path / ".dlpignore").write_text("# comment\n\nbuild/*\n")

    patterns = load_dlpignore(tmp_path)

    assert patterns == ["build/*"]


def test_is_path_ignored_matches_directory_pattern():
    assert is_path_ignored("vendor/lib/secret.txt", ["vendor/*"])
    assert not is_path_ignored("src/app.py", ["vendor/*"])


def test_binary_file_is_skipped(tmp_path: Path):
    target = tmp_path / "blob.bin"
    target.write_bytes(b"\x00\x01\x02AKIAIOSFODNN7EXAMPLE")

    findings = scan_file(target)

    assert findings == []


def test_entropy_detector_can_be_disabled(tmp_path: Path):
    target = tmp_path / "secret.txt"
    target.write_text("TOKEN=kQ7vXz2LpN9wTr4FbHc8Ym1Jd6Ks3EoZa5Vt\n")

    with_entropy = scan_file(target, enable_entropy=True)
    without_entropy = scan_file(target, enable_entropy=False)

    assert any(f.rule_id == "high_entropy_string" for f in with_entropy)
    assert not any(f.rule_id == "high_entropy_string" for f in without_entropy)


@pytest.mark.parametrize(
    "low,high,expected",
    [
        ("low", "low", True),
        ("medium", "low", True),
        ("low", "high", False),
        ("critical", "high", True),
        ("high", "critical", False),
    ],
)
def test_severity_at_least(low, high, expected):
    assert severity.at_least(low, high) is expected


def test_severity_rank_unknown_raises():
    with pytest.raises(ValueError):
        severity.rank("not-a-severity")
