"""Tests for scripts/coverage_badge.py's badge-writing logic."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from coverage_badge import badge_color, write_badge  # noqa: E402


def _write_coverage_json(path: Path, percent: float) -> None:
    path.write_text(json.dumps({"totals": {"percent_covered": percent}}), encoding="utf-8")


def test_badge_color_thresholds():
    assert badge_color(96.9) == "brightgreen"
    assert badge_color(90.0) == "brightgreen"
    assert badge_color(89.9) == "yellow"
    assert badge_color(75.0) == "yellow"
    assert badge_color(74.9) == "red"


def test_write_badge_reads_percent_and_writes_shields_json(tmp_path: Path):
    coverage_json = tmp_path / "coverage.json"
    _write_coverage_json(coverage_json, 96.45)
    output = tmp_path / "badges" / "coverage.json"

    percent = write_badge(coverage_json, output)

    assert percent == 96.45
    badge = json.loads(output.read_text(encoding="utf-8"))
    assert badge == {
        "schemaVersion": 1,
        "label": "coverage",
        "message": "96%",
        "color": "brightgreen",
    }


def test_write_badge_creates_parent_directories(tmp_path: Path):
    coverage_json = tmp_path / "coverage.json"
    _write_coverage_json(coverage_json, 80.0)
    output = tmp_path / "does" / "not" / "exist" / "coverage.json"

    write_badge(coverage_json, output)

    assert output.is_file()
    assert json.loads(output.read_text(encoding="utf-8"))["color"] == "yellow"
