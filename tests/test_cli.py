"""End-to-end CLI behavior: exit codes, --format, --fail-on."""

from __future__ import annotations

from pathlib import Path

from dlp.cli import main


def test_cli_clean_dir_exits_zero(tmp_path: Path, capsys):
    (tmp_path / "clean.txt").write_text("nothing sensitive here\n")

    exit_code = main([str(tmp_path)])

    assert exit_code == 0


def test_cli_fails_on_high_severity_finding(tmp_path: Path, capsys):
    (tmp_path / "creds.txt").write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")

    exit_code = main([str(tmp_path), "--fail-on", "high"])

    assert exit_code == 1


def test_cli_fail_on_none_always_exits_zero(tmp_path: Path, capsys):
    (tmp_path / "creds.txt").write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")

    exit_code = main([str(tmp_path), "--fail-on", "none"])

    assert exit_code == 0


def test_cli_json_format_outputs_valid_json(tmp_path: Path, capsys):
    (tmp_path / "creds.txt").write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")

    main([str(tmp_path), "--format", "json", "--fail-on", "none"])
    captured = capsys.readouterr()

    import json

    findings = json.loads(captured.out)
    assert any(f["rule_id"] == "aws_access_key_id" for f in findings)


def test_cli_fail_on_severity_threshold_respects_low_severity(tmp_path: Path, capsys):
    (tmp_path / "note.txt").write_text("Contact: jane.doe@example.com\n")

    exit_code = main([str(tmp_path), "--fail-on", "medium"])

    assert exit_code == 0
