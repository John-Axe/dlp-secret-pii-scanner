"""End-to-end CLI behavior: exit codes, --format, --fail-on."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from dlp import __version__
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


def test_cli_version_flag_prints_version_and_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_cli_help_epilog_lists_examples_and_exit_codes(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "examples:" in out
    assert "exit codes:" in out


def test_python_dash_m_dlp_runs_as_a_module(tmp_path: Path):
    """`python -m dlp` is a real alternative entry point, not just an
    importable-but-unused __main__.py — invoked via subprocess, not mocked,
    the same way this project's other "does the real thing work" claims
    (the benchmark, the self-scan) are verified rather than asserted."""
    (tmp_path / "creds.txt").write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")

    result = subprocess.run(
        [sys.executable, "-m", "dlp", str(tmp_path), "--fail-on", "high"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "aws_access_key_id" in result.stdout


def test_cli_reports_skipped_files_on_stderr(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setattr("dlp.scanner.MAX_FILE_SIZE_BYTES", 50)
    (tmp_path / "clean.txt").write_text("nothing sensitive\n")  # 18 bytes, under the cap
    (tmp_path / "big.txt").write_text("x" * 200 + "\n")  # 201 bytes, over the cap

    main([str(tmp_path), "--fail-on", "none"])
    captured = capsys.readouterr()

    assert "1 file(s) skipped" in captured.err
    assert "1 too large" in captured.err
    assert "skipped" not in captured.out  # never leaks into the findings stream


def test_cli_says_nothing_about_skips_when_nothing_was_skipped(tmp_path: Path, capsys):
    """Regression guard against the opposite failure mode: printing a
    "0 skipped" line on every ordinary run would just be noise in CI logs
    for the common case."""
    (tmp_path / "clean.txt").write_text("nothing sensitive\n")

    main([str(tmp_path), "--fail-on", "none"])
    captured = capsys.readouterr()

    assert captured.err == ""


def test_cli_json_stdout_stays_valid_json_even_when_files_were_skipped(tmp_path: Path, capsys, monkeypatch):
    """The reason the skip summary goes to stderr, not stdout: --format
    json's stdout is a machine-readable contract (piped into --emit-findings
    consumers, jq, etc.) that can't carry an extra human-readable line."""
    monkeypatch.setattr("dlp.scanner.MAX_FILE_SIZE_BYTES", 50)
    (tmp_path / "creds.txt").write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")  # 39 bytes, under the cap
    (tmp_path / "big.txt").write_text("x" * 200 + "\n")  # 201 bytes, over the cap

    main([str(tmp_path), "--format", "json", "--fail-on", "none"])
    captured = capsys.readouterr()

    findings = json.loads(captured.out)  # raises if stdout isn't clean JSON
    assert any(f["rule_id"] == "aws_access_key_id" for f in findings)
    assert "skipped" in captured.err


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


def test_cli_picks_up_fail_on_from_pyproject_toml(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[tool.dlp]\nfail_on = "low"\n', encoding="utf-8")
    (tmp_path / "note.txt").write_text("Contact: jane.doe@example.com\n")  # a "low"-severity finding

    exit_code = main(["."])  # no --fail-on flag on the CLI at all

    assert exit_code == 1  # config's fail_on=low applies; the hardcoded default (high) would give 0


def test_cli_flag_overrides_pyproject_toml(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[tool.dlp]\nfail_on = "low"\n', encoding="utf-8")
    (tmp_path / "note.txt").write_text("Contact: jane.doe@example.com\n")

    exit_code = main([".", "--fail-on", "critical"])  # explicit flag should win over config

    assert exit_code == 0


def test_cli_no_config_flag_ignores_pyproject_toml(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[tool.dlp]\nfail_on = "low"\n', encoding="utf-8")
    (tmp_path / "note.txt").write_text("Contact: jane.doe@example.com\n")

    exit_code = main([".", "--no-config"])  # falls back to the hardcoded default (high)

    assert exit_code == 0


def test_cli_reports_invalid_config_on_stderr_and_exits_nonzero(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[tool.dlp]\nfail_on = "not-a-real-severity"\n', encoding="utf-8")
    (tmp_path / "clean.txt").write_text("nothing sensitive\n")

    exit_code = main(["."])

    assert exit_code == 1
    assert "fail_on" in capsys.readouterr().err


def test_cli_entropy_threshold_from_config_is_used(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[tool.dlp]\nentropy_threshold = 8.0\n', encoding="utf-8")
    (tmp_path / "secret.txt").write_text("TOKEN=kQ7vXz2LpN9wTr4FbHc8Ym1Jd6Ks3EoZa5Vt\n")  # gitleaks:allow

    main([".", "--format", "json", "--fail-on", "none"])
    findings = json.loads(capsys.readouterr().out)

    # threshold 8.0 is above what this token's entropy reaches, so it's never flagged
    assert not any(f["rule_id"] == "high_entropy_string" for f in findings)


def test_cli_jobs_flag_finds_the_same_findings_as_sequential(tmp_path: Path, capsys):
    (tmp_path / "creds.txt").write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")

    main([str(tmp_path), "--jobs", "2", "--format", "json", "--fail-on", "none"])
    findings = json.loads(capsys.readouterr().out)

    assert any(f["rule_id"] == "aws_access_key_id" for f in findings)


def test_cli_jobs_zero_resolves_to_cpu_count(tmp_path: Path, monkeypatch):
    (tmp_path / "clean.txt").write_text("nothing sensitive\n")
    monkeypatch.setattr("dlp.cli.os.cpu_count", lambda: 6)

    captured_jobs = {}
    from dlp import cli as cli_module

    real_scan_paths = cli_module.scan_paths

    def spying_scan_paths(*args, **kwargs):
        captured_jobs["jobs"] = kwargs.get("jobs")
        return real_scan_paths(*args, **kwargs)

    monkeypatch.setattr(cli_module, "scan_paths", spying_scan_paths)

    main([str(tmp_path), "--jobs", "0", "--fail-on", "none"])

    assert captured_jobs["jobs"] == 6


def test_cli_default_verbosity_shows_neither_config_nor_completion_log(tmp_path: Path, capsys):
    (tmp_path / "clean.txt").write_text("nothing sensitive\n")

    main([str(tmp_path), "--fail-on", "none"])

    assert capsys.readouterr().err == ""


def test_cli_verbose_logs_resolved_config_and_completion_summary(tmp_path: Path, capsys):
    (tmp_path / "clean.txt").write_text("nothing sensitive\n")

    main([str(tmp_path), "-v", "--fail-on", "none"])
    err = capsys.readouterr().err

    assert "format=table" in err
    assert "fail_on=none" in err
    assert "jobs=1" in err
    assert "scan complete: 0 finding(s)" in err


def test_cli_verbose_notes_when_a_config_file_was_loaded(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[tool.dlp]\nfail_on = "low"\n', encoding="utf-8")
    (tmp_path / "clean.txt").write_text("nothing sensitive\n")

    main([".", "-v", "--fail-on", "none"])

    assert "config file loaded" in capsys.readouterr().err


def test_cli_double_verbose_still_shows_info_level_output(tmp_path: Path, capsys):
    """-vv (DEBUG) doesn't add distinct content over -v (INFO) yet - this
    pins that -vv is still at least as verbose as -v, not accidentally
    quieter, which the raw >= 2 comparison in _configure_logging could get
    backwards in a future edit without a test catching it."""
    (tmp_path / "clean.txt").write_text("nothing sensitive\n")

    main([str(tmp_path), "-vv", "--fail-on", "none"])

    assert "scan complete" in capsys.readouterr().err


def test_cli_quiet_suppresses_the_skipped_files_warning(tmp_path: Path, capsys):
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01binary")

    main([str(tmp_path), "-q", "--fail-on", "none"])

    assert capsys.readouterr().err == ""


def test_cli_quiet_and_verbose_together_quiet_wins(tmp_path: Path, capsys):
    """-q raises the level to ERROR regardless of how many -v's were also
    given - quiet is an explicit "I don't want this noise" request and
    should not be overridable by also passing -v, whichever order."""
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01binary")

    main([str(tmp_path), "-vv", "-q", "--fail-on", "none"])

    assert capsys.readouterr().err == ""
