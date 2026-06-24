"""Severity levels and ordering used for --fail-on comparisons."""

from __future__ import annotations

ORDER = ["low", "medium", "high", "critical"]


def rank(severity: str) -> int:
    try:
        return ORDER.index(severity.lower())
    except ValueError as exc:
        raise ValueError(f"unknown severity: {severity!r}") from exc


def at_least(severity: str, threshold: str) -> bool:
    """True if severity is >= threshold in the ORDER scale."""
    return rank(severity) >= rank(threshold)
