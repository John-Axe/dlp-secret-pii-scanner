"""Performance regression guard, not a throughput benchmark - see
benchmark/run_throughput_benchmark.py for actual files/sec, MB/sec
measurement (deliberately not CI-gated, since wall-clock throughput is
machine-dependent in a way these bounds are careful not to be).

The bounds here are generous on purpose - 10-100x what a healthy run
actually takes on this environment - because the point isn't "is this
fast," it's "did a change make this catastrophically, not just
incrementally, slower." The engineering audit named this exact gap: a
future change that makes a regex backtrack exponentially would previously
have passed CI silently, since nothing measured scan wall-time at all.
"""

from __future__ import annotations

import time
from pathlib import Path

from dlp.scanner import scan_file, scan_paths

# Deliberately generous - see module docstring. A real ReDoS blowup is
# orders of magnitude slower than this, not a close call.
CATASTROPHE_THRESHOLD_SECONDS = 10.0


def test_many_files_do_not_catastrophically_regress(tmp_path: Path):
    for i in range(300):
        (tmp_path / f"file_{i}.txt").write_text(
            "normal log line with some words and an occasional AKIAIOSFODNN7EXAMPLE\n" * 5
        )

    start = time.perf_counter()
    scan_paths([tmp_path])
    elapsed = time.perf_counter() - start

    assert elapsed < CATASTROPHE_THRESHOLD_SECONDS, (
        f"Scanning 300 small files took {elapsed:.2f}s - expected well under "
        f"{CATASTROPHE_THRESHOLD_SECONDS}s. This threshold is generous by design; "
        "blowing through it points at a real regression (e.g. a detector regex "
        "that started backtracking catastrophically), not normal variance."
    )


def test_pathologically_long_single_line_does_not_catastrophically_regress(tmp_path: Path):
    """Targets the specific failure mode a hand-review can't easily catch:
    a regex that's fine against realistic line lengths but backtracks
    exponentially against a long adversarial one. None of the current
    detector patterns have nested unbounded quantifiers (the classic ReDoS
    shape, e.g. `(a+)+`), so this is expected to pass comfortably today -
    its job is catching a *future* change that introduces one.
    """
    # Mixes digits/dashes/spaces to stress credit_card's (?:\d[ -]?){13,19}
    # and quote-adjacent characters to stress generic_password's
    # [^\s"'][^"'\n]{5,} - the two patterns with the least-bounded classes.
    adversarial_line = ("1 2-3 4-5 6-7 8-9 0-1 2-3 " * 2000) + ('pwd="' + "a" * 50_000 + '"')
    target = tmp_path / "adversarial.txt"
    target.write_text(adversarial_line)

    start = time.perf_counter()
    scan_file(target)
    elapsed = time.perf_counter() - start

    assert elapsed < CATASTROPHE_THRESHOLD_SECONDS, (
        f"Scanning one adversarial ~350KB line took {elapsed:.2f}s - expected well "
        f"under {CATASTROPHE_THRESHOLD_SECONDS}s. See test docstring."
    )
