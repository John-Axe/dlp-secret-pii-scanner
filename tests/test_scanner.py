"""Tests for the file/tree scanner, ignore mechanism, and severity gating."""

from __future__ import annotations

from pathlib import Path

import pytest

from dlp import severity
from dlp.ignore import is_path_ignored, load_dlpignore
from dlp.scanner import ScanStats, scan_file, scan_paths


class _UnreadablePath:
    """Stands in for a Path whose .open() raises OSError - a permission-
    denied file, or one removed between listing and reading (a TOCTOU race
    in a full-tree scan). Real permission bits are unreliable to test
    against directly (root ignores them; behavior varies by CI runner);
    this deterministically exercises the same `except OSError` branch
    scan_file actually has, regardless of environment.
    """

    def open(self, *args, **kwargs):
        raise OSError("permission denied")


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
    stats = ScanStats()

    findings = scan_file(target, stats=stats)

    assert findings == []
    assert stats.files_skipped_binary == 1
    assert stats.files_scanned == 0


def test_unreadable_file_is_skipped_and_counted_not_silently_dropped():
    """The bug this pins: scan_file's `except OSError: return []` used to
    make a permission-denied or race-deleted file indistinguishable from a
    clean file with no findings - both just produced []. Now it's visible
    in stats instead."""
    stats = ScanStats()

    findings = scan_file(_UnreadablePath(), display_path="secret.txt", stats=stats)

    assert findings == []
    assert stats.files_skipped_unreadable == 1
    assert stats.files_scanned == 0


def test_oversized_file_is_skipped_and_counted_not_silently_dropped(tmp_path, monkeypatch):
    """The other bug this pins: a file over MAX_FILE_SIZE_BYTES used to be
    silently indistinguishable from a clean file - same [] either way. Uses
    a monkeypatched, tiny size cap rather than writing literal megabytes to
    disk, but exercises the exact same size-check branch."""
    monkeypatch.setattr("dlp.scanner.MAX_FILE_SIZE_BYTES", 10)
    target = tmp_path / "big.txt"
    target.write_text("this file is well over ten bytes long\n")
    stats = ScanStats()

    findings = scan_file(target, stats=stats)

    assert findings == []
    assert stats.files_skipped_too_large == 1
    assert stats.files_scanned == 0


def test_scan_stats_total_skipped_sums_all_skip_reasons():
    stats = ScanStats(files_skipped_too_large=1, files_skipped_binary=2, files_skipped_unreadable=3)
    assert stats.total_skipped == 6


def test_scan_paths_aggregates_stats_across_multiple_files(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("dlp.scanner.MAX_FILE_SIZE_BYTES", 10)
    (tmp_path / "clean.txt").write_text("short\n")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02binary")
    (tmp_path / "big.txt").write_text("this file is well over ten bytes long\n")
    stats = ScanStats()

    scan_paths([tmp_path], stats=stats)

    assert stats.files_scanned == 1
    assert stats.files_skipped_binary == 1
    assert stats.files_skipped_too_large == 1
    assert stats.total_skipped == 2


def test_scan_file_without_stats_arg_behaves_exactly_as_before(tmp_path: Path):
    """stats is optional and defaults to None - every pre-existing call site
    (and most of this file's other tests) doesn't pass it. Confirms that
    path still works with zero behavior change."""
    target = tmp_path / "blob.bin"
    target.write_bytes(b"\x00\x01\x02AKIAIOSFODNN7EXAMPLE")

    findings = scan_file(target)

    assert findings == []


def test_scan_paths_applies_dlpignore_to_individual_files_with_shared_ignore_root(tmp_path: Path):
    (tmp_path / ".dlpignore").write_text("tests/*\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    ignored_file = tests_dir / "fixture.py"
    ignored_file.write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")
    kept_file = tmp_path / "app.py"
    kept_file.write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")

    findings = scan_paths([ignored_file, kept_file], ignore_root=tmp_path)

    files_with_findings = {f.file for f in findings}
    assert not any("fixture.py" in f for f in files_with_findings)
    assert any("app.py" in f for f in files_with_findings)


def test_scan_paths_without_ignore_root_falls_back_to_per_file_parent(tmp_path: Path):
    (tmp_path / ".dlpignore").write_text("tests/*\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    target = tests_dir / "fixture.py"
    target.write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")

    findings = scan_paths([target])

    assert any(f.rule_id == "aws_access_key_id" for f in findings)


def test_entropy_detector_can_be_disabled(tmp_path: Path):
    target = tmp_path / "secret.txt"
    target.write_text("TOKEN=kQ7vXz2LpN9wTr4FbHc8Ym1Jd6Ks3EoZa5Vt\n")  # gitleaks:allow

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


def test_severity_at_least_none_raises():
    with pytest.raises(ValueError):
        severity.at_least("low", "none")


def test_has_inline_ignore_requires_comment_marker(tmp_path):
    target = tmp_path / "code.py"
    target.write_text(
        'dlp_ignore_var = "AKIAIOSFODNN7EXAMPLE"\n'
        'real_key = "AKIAIOSFODNN7EXAMPLE"  # dlp-ignore\n'
    )
    findings = scan_file(target)
    lines = {f.line for f in findings if f.rule_id == "aws_access_key_id"}
    assert 1 in lines
    assert 2 not in lines


def test_is_path_ignored_windows_backslash():
    assert is_path_ignored("vendor\\lib\\secret.txt", ["vendor/*"])


def test_fingerprint_stable_across_line_number_changes(tmp_path):
    secret = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
    f1 = (tmp_path / "a.txt")
    f1.write_text(f"{secret}\n")
    f2 = (tmp_path / "b.txt")
    f2.write_text(f"# comment\n# comment\n{secret}\n")

    fp1 = scan_file(f1, display_path="same.txt")[0].fingerprint
    fp2 = scan_file(f2, display_path="same.txt")[0].fingerprint
    assert fp1 == fp2


def test_scan_file_skips_symlinks(tmp_path):
    real = tmp_path / "real.txt"
    real.write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")
    link = tmp_path / "link.txt"
    link.symlink_to(real)

    findings = scan_paths([tmp_path])
    filenames = {Path(f.file).name for f in findings}
    assert "link.txt" not in filenames
    assert "real.txt" in filenames
