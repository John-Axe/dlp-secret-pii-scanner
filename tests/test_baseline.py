"""Tests for baseline mode: fingerprinting and known-finding suppression."""

from __future__ import annotations

from pathlib import Path

from dlp import baseline
from dlp.scanner import scan_file


def test_fingerprint_is_stable_for_same_finding(tmp_path: Path):
    target = tmp_path / "creds.txt"
    target.write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")

    first = scan_file(target, display_path="creds.txt")
    second = scan_file(target, display_path="creds.txt")

    assert first[0].fingerprint == second[0].fingerprint


def test_fingerprint_differs_for_different_rule_or_file(tmp_path: Path):
    target = tmp_path / "creds.txt"
    target.write_text(
        "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n"
        'token = "ghp_00000000000000000000000000000000000A"\n'
    )

    findings = scan_file(target, display_path="creds.txt")
    fingerprints = {f.fingerprint for f in findings}

    assert len(fingerprints) == len(findings)


def test_write_and_load_baseline_round_trips(tmp_path: Path):
    target = tmp_path / "creds.txt"
    target.write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")
    findings = scan_file(target, display_path="creds.txt")

    baseline_path = tmp_path / "baseline.json"
    baseline.write_baseline(baseline_path, findings)
    loaded = baseline.load_baseline(baseline_path)

    assert loaded == {f.fingerprint for f in findings}


def test_load_baseline_missing_file_returns_empty_set(tmp_path: Path):
    assert baseline.load_baseline(tmp_path / "does-not-exist.json") == set()


def test_filter_known_excludes_matching_fingerprints(tmp_path: Path):
    target = tmp_path / "creds.txt"
    target.write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")
    findings = scan_file(target, display_path="creds.txt")
    known = {findings[0].fingerprint}

    remaining = baseline.filter_known(findings, known)

    assert remaining == []


def test_filter_known_keeps_unmatched_findings(tmp_path: Path):
    target = tmp_path / "creds.txt"
    target.write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")
    findings = scan_file(target, display_path="creds.txt")

    remaining = baseline.filter_known(findings, {"not-a-real-fingerprint"})

    assert remaining == findings
