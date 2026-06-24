"""Tests for the precision/recall/F1 math used by benchmark/run_benchmark.py,
and an end-to-end check that the shipped corpus clears the documented gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "benchmark"))

from run_benchmark import evaluate, precision_recall_f1  # noqa: E402


def test_precision_recall_f1_perfect():
    precision, recall, f1 = precision_recall_f1(tp=10, fp=0, fn=0)
    assert precision == 1.0
    assert recall == 1.0
    assert f1 == 1.0


def test_precision_recall_f1_with_false_positives():
    precision, recall, f1 = precision_recall_f1(tp=9, fp=1, fn=0)
    assert precision == 0.9
    assert recall == 1.0
    assert round(f1, 4) == round(2 * 0.9 * 1.0 / (0.9 + 1.0), 4)


def test_precision_recall_f1_with_false_negatives():
    precision, recall, f1 = precision_recall_f1(tp=8, fp=0, fn=2)
    assert precision == 1.0
    assert recall == 0.8


def test_precision_recall_f1_no_signal_defaults_to_perfect():
    precision, recall, f1 = precision_recall_f1(tp=0, fp=0, fn=0)
    assert precision == 1.0
    assert recall == 1.0
    assert f1 == 1.0


def test_shipped_corpus_clears_documented_gate():
    results = evaluate()
    per_rule = results["per_rule"]
    total_tp = sum(c["tp"] for c in per_rule.values())
    total_fp = sum(c["fp"] for c in per_rule.values())
    total_fn = sum(c["fn"] for c in per_rule.values())
    precision, recall, _ = precision_recall_f1(total_tp, total_fp, total_fn)

    assert precision >= 0.85
    assert recall >= 0.85
    assert total_tp > 0
