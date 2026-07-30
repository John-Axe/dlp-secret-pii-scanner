"""Scans benchmark/corpus, compares findings against benchmark/labels.json,
and prints a precision/recall/F1 table per detector and overall.

Ground truth is per (file, rule_id): does this file contain a planted
artifact that this rule should catch? A rule firing on a file where it
isn't expected counts as a false positive, even if other rules correctly
catch the same artifact - this keeps the benchmark honest about each
detector's individual signal quality.

Exits non-zero (failing CI) if overall precision drops below --min-precision.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

BENCHMARK_DIR = Path(__file__).resolve().parent
REPO_ROOT = BENCHMARK_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from dlp.scanner import scan_file  # noqa: E402


def load_labels() -> dict[str, list[str]]:
    with open(BENCHMARK_DIR / "labels.json", encoding="utf-8") as fh:
        return json.load(fh)


def corpus_files() -> list[Path]:
    corpus_dir = BENCHMARK_DIR / "corpus"
    files = []
    for sub in ("positives", "negatives"):
        files.extend(sorted((corpus_dir / sub).glob("*")))
    return [f for f in files if f.is_file()]


def evaluate() -> dict:
    labels = load_labels()
    corpus_dir = BENCHMARK_DIR / "corpus"

    per_rule = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    false_positive_details: list[tuple[str, str]] = []
    false_negative_details: list[tuple[str, str]] = []

    for file_path in corpus_files():
        rel = file_path.relative_to(corpus_dir).as_posix()
        expected = set(labels.get(rel, []))
        findings = scan_file(file_path, display_path=rel)
        actual = {f.rule_id for f in findings}

        for rule_id in expected & actual:
            per_rule[rule_id]["tp"] += 1
        for rule_id in actual - expected:
            per_rule[rule_id]["fp"] += 1
            false_positive_details.append((rel, rule_id))
        for rule_id in expected - actual:
            per_rule[rule_id]["fn"] += 1
            false_negative_details.append((rel, rule_id))

    return {
        "per_rule": dict(per_rule),
        "false_positives": false_positive_details,
        "false_negatives": false_negative_details,
    }


def precision_recall_f1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def render_table(results: dict) -> tuple[str, float, float, float]:
    per_rule = results["per_rule"]
    headers = ["RULE", "TP", "FP", "FN", "PRECISION", "RECALL", "F1"]
    rows = []
    total_tp = total_fp = total_fn = 0
    for rule_id in sorted(per_rule):
        counts = per_rule[rule_id]
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        total_tp += tp
        total_fp += fp
        total_fn += fn
        precision, recall, f1 = precision_recall_f1(tp, fp, fn)
        rows.append([rule_id, str(tp), str(fp), str(fn), f"{precision:.2f}", f"{recall:.2f}", f"{f1:.2f}"])

    overall_p, overall_r, overall_f1 = precision_recall_f1(total_tp, total_fp, total_fn)
    rows.append(
        [
            "OVERALL",
            str(total_tp),
            str(total_fp),
            str(total_fn),
            f"{overall_p:.2f}",
            f"{overall_r:.2f}",
            f"{overall_f1:.2f}",
        ]
    )

    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

    def fmt(cells: list[str]) -> str:
        return "  ".join(cell.ljust(w) for cell, w in zip(cells, widths, strict=True))

    lines = [fmt(headers), fmt(["-" * w for w in widths])]
    lines.extend(fmt(r) for r in rows)

    if results["false_positives"]:
        lines.append("\nFalse positives:")
        lines.extend(f"  {file} -> {rule_id}" for file, rule_id in results["false_positives"])
    if results["false_negatives"]:
        lines.append("\nFalse negatives (missed detections):")
        lines.extend(f"  {file} -> {rule_id}" for file, rule_id in results["false_negatives"])

    return "\n".join(lines), overall_p, overall_r, overall_f1


def badge_color(precision: float) -> str:
    if precision >= 0.9:
        return "brightgreen"
    if precision >= 0.75:
        return "yellow"
    return "red"


def write_badge(path: Path, precision: float, recall: float, f1: float) -> None:
    """Writes a shields.io endpoint-badge JSON
    (https://shields.io/badges/endpoint-badge) so the README badge always
    reflects the most recent benchmark run instead of a hand-typed number.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schemaVersion": 1,
        "label": "dlp-scan benchmark",
        "message": f"precision {precision:.0%} · recall {recall:.0%} · f1 {f1:.0%}",
        "color": badge_color(precision),
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the DLP scanner benchmark.")
    parser.add_argument(
        "--min-precision",
        type=float,
        default=0.85,
        help="Fail (exit 1) if overall precision drops below this (default: 0.85).",
    )
    parser.add_argument(
        "--min-recall",
        type=float,
        default=0.85,
        help="Fail (exit 1) if overall recall drops below this (default: 0.85).",
    )
    parser.add_argument(
        "--badge-output",
        type=Path,
        default=None,
        help="Write a shields.io endpoint-badge JSON with the current precision/recall/f1 "
        "to this path (e.g. .github/badges/benchmark.json).",
    )
    args = parser.parse_args(argv)

    results = evaluate()
    table, precision, recall, f1 = render_table(results)
    print(table)
    print(f"\nOverall precision={precision:.2%} recall={recall:.2%} f1={f1:.2%}")

    if args.badge_output:
        write_badge(args.badge_output, precision, recall, f1)
        print(f"\nWrote badge data to {args.badge_output}")

    if precision < args.min_precision:
        print(
            f"\nFAIL: precision {precision:.2%} is below the required minimum {args.min_precision:.2%}",
            file=sys.stderr,
        )
        return 1
    if recall < args.min_recall:
        print(
            f"\nFAIL: recall {recall:.2%} is below the required minimum {args.min_recall:.2%}",
            file=sys.stderr,
        )
        return 1

    print("\nPASS: benchmark thresholds met.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
