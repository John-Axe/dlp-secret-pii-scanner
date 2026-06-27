"""End-to-end CLI behavior: exit codes, --format, --fail-on."""

from __future__ import annotations

import json
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

    findings = json.loads(captured.out)
    assert any(f["rule_id"] == "aws_access_key_id" for f in findings)


def test_cli_fail_on_severity_threshold_respects_low_severity(tmp_path: Path, capsys):
    (tmp_path / "note.txt").write_text("Contact: jane.doe@example.com\n")

    exit_code = main([str(tmp_path), "--fail-on", "medium"])

    assert exit_code == 0


def test_cli_sarif_format_outputs_valid_sarif(tmp_path: Path, capsys):
    (tmp_path / "creds.txt").write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")

    main([str(tmp_path), "--format", "sarif", "--fail-on", "none"])
    captured = capsys.readouterr()

    sarif = json.loads(captured.out)
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["results"][0]["ruleId"] == "aws_access_key_id"


def test_cli_write_baseline_then_baseline_suppresses_known_finding(tmp_path: Path, capsys):
    (tmp_path / "creds.txt").write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")
    baseline_path = tmp_path / "baseline.json"

    exit_code = main([str(tmp_path), "--write-baseline", str(baseline_path)])
    assert exit_code == 0
    assert baseline_path.is_file()
    capsys.readouterr()

    exit_code = main(
        [str(tmp_path), "--baseline", str(baseline_path), "--fail-on", "high", "--format", "json"]
    )
    captured = capsys.readouterr()

    findings = json.loads(captured.out)
    assert findings == []
    assert exit_code == 0


def test_cli_baseline_does_not_suppress_new_findings(tmp_path: Path, capsys):
    (tmp_path / "creds.txt").write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")
    baseline_path = tmp_path / "baseline.json"
    main([str(tmp_path), "--write-baseline", str(baseline_path)])

    (tmp_path / "other.txt").write_text("GITHUB_TOKEN=ghp_00000000000000000000000000000000000A\n")

    exit_code = main([str(tmp_path), "--baseline", str(baseline_path), "--fail-on", "high"])

    assert exit_code == 1


def test_cli_diff_only_scans_only_changed_files(tmp_path: Path, capsys, monkeypatch):
    changed_file = tmp_path / "changed.txt"
    changed_file.write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")
    (tmp_path / "untouched.txt").write_text("GITHUB_TOKEN=ghp_00000000000000000000000000000000000A\n")

    from dlp import cli as cli_module

    monkeypatch.setattr(cli_module.diff, "changed_files", lambda base_ref, root: [changed_file])
    monkeypatch.chdir(tmp_path)

    main(["--diff-only", "--format", "json", "--fail-on", "none"])
    captured = capsys.readouterr()

    findings = json.loads(captured.out)
    assert all(f["rule_id"] == "aws_access_key_id" for f in findings)
    assert findings


def test_cli_diff_only_no_changed_files_means_no_findings(tmp_path: Path, capsys, monkeypatch):
    from dlp import cli as cli_module

    monkeypatch.setattr(cli_module.diff, "changed_files", lambda base_ref, root: [])
    monkeypatch.chdir(tmp_path)

    exit_code = main(["--diff-only", "--fail-on", "high"])

    assert exit_code == 0


def test_cli_no_entropy_flag(tmp_path: Path, capsys):
    (tmp_path / "secret.txt").write_text("TOKEN=kQ7vXz2LpN9wTr4FbHc8Ym1Jd6Ks3EoZa5Vt\n")  # gitleaks:allow

    main([str(tmp_path), "--no-entropy", "--format", "json", "--fail-on", "none"])
    findings = json.loads(capsys.readouterr().out)

    assert not any(f["rule_id"] == "high_entropy_string" for f in findings)


def test_cli_entropy_threshold_excludes_below_threshold(tmp_path: Path, capsys):
    (tmp_path / "secret.txt").write_text("TOKEN=kQ7vXz2LpN9wTr4FbHc8Ym1Jd6Ks3EoZa5Vt\n")  # gitleaks:allow

    main([str(tmp_path), "--entropy-threshold", "6.0", "--format", "json", "--fail-on", "none"])
    findings = json.loads(capsys.readouterr().out)

    assert not any(f["rule_id"] == "high_entropy_string" for f in findings)


def test_cli_table_format(tmp_path: Path, capsys):
    (tmp_path / "creds.txt").write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")

    main([str(tmp_path), "--format", "table", "--fail-on", "none"])
    out = capsys.readouterr().out

    assert "SEVERITY" in out
    assert "aws_access_key_id" in out


def test_cli_diff_only_with_baseline(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    changed = tmp_path / "changed.txt"
    changed.write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")
    baseline_path = tmp_path / "baseline.json"

    main([".", "--write-baseline", str(baseline_path)])
    capsys.readouterr()

    from dlp import cli as cli_module

    monkeypatch.setattr(cli_module.diff, "changed_files", lambda base_ref, root: [changed])

    main(["--diff-only", "--baseline", str(baseline_path), "--format", "json", "--fail-on", "none"])
    findings = json.loads(capsys.readouterr().out)

    assert findings == []
