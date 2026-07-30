"""Measures scan throughput (files/sec, MB/sec) and peak process memory
(RSS) against a synthetic corpus, generated on the fly rather than
committed to the repo as fixture data - this is a diagnostic tool, not the
accuracy benchmark (see run_benchmark.py for that), and doesn't need a
hand-labeled ground truth.

Deliberately NOT a CI-gating pass/fail check the way run_benchmark.py's
precision/recall thresholds are: wall-clock throughput is machine-dependent
in a way accuracy against a fixed corpus isn't, so a hard numeric threshold
here would be comparing this run's hardware against whatever produced the
last committed number, not measuring a real regression. Run manually, or
compare successive runs on the same machine. tests/test_performance_smoke.py
carries the actual CI-gated regression guard - a generous ceiling meant to
catch a catastrophic regression (e.g. an accidentally ReDoS-prone regex),
not to enforce a specific throughput number.
"""

from __future__ import annotations

import argparse
import random
import sys
import tempfile
import time
from pathlib import Path

try:
    import resource  # POSIX-only - no stdlib equivalent on Windows.
except ImportError:  # pragma: no cover - exercised only on a non-POSIX platform
    resource = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from dlp.scanner import scan_paths  # noqa: E402

_WORDS = (
    "the quick brown fox jumps over lazy dog while system configuration "
    "loads default settings from the environment and validates every "
    "incoming request against the schema before writing results to disk"
).split()

_FAKE_SECRET_LINE = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"  # dlp-ignore


def _secret_interval(lines_per_file: int) -> int:
    """One planted secret roughly every 20 lines, but never so sparse that a
    small --lines-per-file plants zero per file - a fixed interval (the
    previous version used a hardcoded 137) silently plants nothing at all
    once lines_per_file drops below it, which is exactly what happened with
    this script's own default of 80 before this fix.
    """
    return max(1, min(20, lines_per_file))


def _generate_file(rng: random.Random, lines_per_file: int, interval: int) -> tuple[str, int]:
    lines = []
    planted = 0
    for i in range(lines_per_file):
        if i > 0 and i % interval == 0:
            lines.append(_FAKE_SECRET_LINE)
            planted += 1
        else:
            lines.append(" ".join(rng.choices(_WORDS, k=rng.randint(6, 16))))
    return "\n".join(lines) + "\n", planted


def generate_corpus(root: Path, *, num_files: int, lines_per_file: int, seed: int) -> tuple[int, int]:
    """Writes num_files synthetic files under root. Returns (total_bytes, total_planted_secrets)."""
    rng = random.Random(seed)
    interval = _secret_interval(lines_per_file)
    total_bytes = 0
    total_planted = 0
    for i in range(num_files):
        content, planted = _generate_file(rng, lines_per_file, interval)
        path = root / f"synthetic_{i:05d}.txt"
        path.write_text(content, encoding="utf-8")
        total_bytes += len(content.encode("utf-8"))
        total_planted += planted
    return total_bytes, total_planted


def peak_rss_mb() -> float | None:
    """Process peak resident set size in MB since interpreter start, or None
    on a platform with no `resource` module (Windows).

    This is the *whole process's* peak RSS, not a scan-isolated delta - the
    stdlib has no cheap POSIX equivalent for "memory used by just this call,"
    so it's informative for "does memory stay bounded as corpus size grows,"
    not a precise per-scan measurement. `ru_maxrss` units differ by platform
    (KB on Linux, bytes on macOS) - a real, easy-to-get-wrong inconsistency,
    normalized here rather than left to the caller.
    """
    if resource is None:
        return None
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return raw / (1024 * 1024) if sys.platform == "darwin" else raw / 1024


def run(num_files: int, lines_per_file: int, seed: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="dlp-throughput-") as tmp:
        root = Path(tmp)
        total_bytes, total_planted = generate_corpus(
            root, num_files=num_files, lines_per_file=lines_per_file, seed=seed
        )

        start = time.perf_counter()
        findings = scan_paths([root])
        elapsed = time.perf_counter() - start

    return {
        "files": num_files,
        "bytes": total_bytes,
        "planted_secrets": total_planted,
        "findings": len(findings),
        "elapsed_seconds": elapsed,
        "files_per_second": num_files / elapsed if elapsed > 0 else float("inf"),
        "mb_per_second": (total_bytes / (1024 * 1024)) / elapsed if elapsed > 0 else float("inf"),
        "peak_rss_mb": peak_rss_mb(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure dlp-scan throughput against a synthetic corpus.")
    parser.add_argument("--num-files", type=int, default=2000, help="Synthetic files to generate (default: 2000).")
    parser.add_argument(
        "--lines-per-file", type=int, default=80, help="Lines per synthetic file (default: 80)."
    )
    parser.add_argument("--seed", type=int, default=0, help="RNG seed, for reproducible corpora (default: 0).")
    args = parser.parse_args(argv)

    result = run(args.num_files, args.lines_per_file, args.seed)

    print(f"Synthetic corpus: {result['files']} files, {result['bytes'] / (1024 * 1024):.2f} MB")
    print(f"Findings:         {result['findings']} (expected: {result['planted_secrets']} planted)")
    print(f"Elapsed:          {result['elapsed_seconds']:.3f}s")
    print(f"Throughput:       {result['files_per_second']:.1f} files/sec, {result['mb_per_second']:.2f} MB/sec")
    if result["peak_rss_mb"] is not None:
        print(
            f"Peak RSS:         {result['peak_rss_mb']:.1f} MB (whole process since start, "
            "not scan-isolated - see peak_rss_mb()'s docstring)"
        )
    else:
        print("Peak RSS:         not measured on this platform (no `resource` module)")
    if result["findings"] != result["planted_secrets"]:
        print(
            f"\nWARNING: found {result['findings']}, planted {result['planted_secrets']} - "
            "the corpus generator or a detector regressed; timing numbers above are still "
            "informative, but this specific run's finding count doesn't match what was planted.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
