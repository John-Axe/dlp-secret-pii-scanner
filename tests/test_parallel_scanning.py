"""Tests for scan_paths(..., jobs=N). Kept in their own file rather than
folded into test_scanner.py: these spawn real worker processes (not
mocked - a mocked ProcessPoolExecutor wouldn't actually prove pickling and
cross-process stats-merging work), so they're slower and conceptually
distinct from the rest of the scanner suite.

The one property that matters more than any other here: for the same
input, jobs=N must produce the exact same findings, in the exact same
order, with the exact same ScanStats totals, as jobs=1. Every test below
exists to pin down one facet of that.
"""

from __future__ import annotations

from pathlib import Path

from dlp.scanner import ScanStats, scan_paths


def _build_mixed_corpus(root: Path) -> None:
    """A deliberately non-trivial layout: multiple subdirectories (so file
    discovery order isn't trivially the same as creation order), a mix of
    files with findings and without, plus one binary and one oversized file
    to exercise ScanStats' skip-counting across the process boundary.
    """
    for sub in ("a", "b", "c"):
        (root / sub).mkdir()
    for i in range(15):
        sub = ("a", "b", "c")[i % 3]
        target = root / sub / f"file_{i:03d}.py"
        if i % 4 == 0:
            target.write_text(f"AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE  # file {i}\n")
        else:
            target.write_text(f"nothing sensitive here, file {i}\n" * 3)
    (root / "blob.bin").write_bytes(b"\x00\x01\x02binary content, not scanned")


def test_jobs_1_is_identical_to_omitting_jobs_entirely(tmp_path: Path):
    """Regression guard for the scan_paths refactor this parameter required
    (file discovery split from scanning) - jobs defaults to 1, and that
    path must be byte-for-byte what existed before this parameter did."""
    _build_mixed_corpus(tmp_path)

    explicit = scan_paths([tmp_path], jobs=1)
    implicit = scan_paths([tmp_path])

    assert explicit == implicit
    assert len(explicit) > 0  # sanity: the corpus actually has findings to compare


def test_parallel_scan_matches_sequential_findings_exactly_in_order(tmp_path: Path):
    _build_mixed_corpus(tmp_path)

    sequential = scan_paths([tmp_path], jobs=1)
    parallel = scan_paths([tmp_path], jobs=3)

    assert parallel == sequential  # not just same length - same Findings, same order


def test_parallel_scan_stats_match_sequential_stats(tmp_path: Path):
    """Uses a real oversized file against the real MAX_FILE_SIZE_BYTES,
    deliberately not a monkeypatched threshold: this test itself caught a
    real gotcha while being written - Python 3.14's ProcessPoolExecutor
    defaults to the 'forkserver' start method, which does NOT propagate a
    module-global mutated via monkeypatch *after* the pool exists into
    worker processes (they're forked from the forkserver's own already-
    established state, not from a live snapshot of the parent at task-
    submission time). That's a real multiprocessing behavior worth knowing,
    not a scan_paths bug - but it means comparing stats across sequential
    vs. parallel has to hold every input constant via real file conditions,
    not a mutated global that only one of the two paths would ever see.
    """
    _build_mixed_corpus(tmp_path)
    (tmp_path / "a" / "big.txt").write_bytes(b"x" * (6 * 1024 * 1024))  # over the real 5MB cap

    sequential_stats = ScanStats()
    scan_paths([tmp_path], jobs=1, stats=sequential_stats)

    parallel_stats = ScanStats()
    scan_paths([tmp_path], jobs=3, stats=parallel_stats)

    assert parallel_stats == sequential_stats
    assert parallel_stats.files_skipped_binary == 1
    assert parallel_stats.files_skipped_too_large == 1
    assert parallel_stats.files_scanned > 0


def test_jobs_greater_than_file_count_does_not_error(tmp_path: Path):
    """More workers than files is a real, easy-to-hit case (--jobs 0 on a
    machine with many cores, scanning a small --diff-only PR) - must not
    error or hang, just work with idle workers."""
    (tmp_path / "one.txt").write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")

    findings = scan_paths([tmp_path], jobs=16)

    assert len(findings) == 1


def test_jobs_with_empty_file_list_does_not_error(tmp_path: Path):
    findings = scan_paths([tmp_path], jobs=4)
    assert findings == []
