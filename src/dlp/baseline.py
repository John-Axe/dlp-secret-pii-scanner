"""Baseline mode: suppress known findings (by Finding.fingerprint) from
output and from the --fail-on gate, so only newly introduced secrets fail
the build. Same idea as detect-secrets' baseline file.
"""

from __future__ import annotations

import json
from pathlib import Path

from .scanner import Finding


def load_baseline(path: Path) -> set[str]:
    path = Path(path)
    if not path.is_file():
        return set()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Baseline file '{path}' contains invalid JSON: {exc}") from exc
    return set(data.get("fingerprints", []))


def write_baseline(path: Path, findings: list[Finding]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"fingerprints": sorted({f.fingerprint for f in findings})}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def filter_known(findings: list[Finding], known_fingerprints: set[str]) -> list[Finding]:
    return [f for f in findings if f.fingerprint not in known_fingerprints]
