"""Regex and entropy detectors for secrets and PII.

Each detector is a `Detector` instance with a stable `rule_id` (used by the
benchmark labels and --fail-on logic) and a `scan_line` method that returns
zero or more `Match` tuples: (start, end, matched_text).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Detector:
    rule_id: str
    name: str
    severity: str
    pattern: "re.Pattern[str]"
    validator: "callable | None" = None

    def scan_line(self, line: str) -> list[Match]:
        matches = []
        for m in self.pattern.finditer(line):
            text = m.group(0)
            if self.validator is not None and not self.validator(text, m):
                continue
            matches.append(Match(m.start(), m.end(), text))
        return matches


def _luhn_ok(text: str, m: "re.Match[str]") -> bool:
    digits = [int(c) for c in text if c.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _ssn_ok(text: str, m: "re.Match[str]") -> bool:
    area, group, serial = m.group(1), m.group(2), m.group(3)
    if area in ("000", "666") or area.startswith("9"):
        return False
    if group == "00" or serial == "0000":
        return False
    return True


REGEX_DETECTORS: list[Detector] = [
    Detector(
        rule_id="aws_access_key_id",
        name="AWS Access Key ID",
        severity="high",
        pattern=re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)[0-9A-Z]{16}\b"),
    ),
    Detector(
        rule_id="aws_secret_key",
        name="AWS Secret Access Key",
        severity="critical",
        pattern=re.compile(
            r"(?i)aws_secret_access_key\s*[=:]\s*[\"']?([A-Za-z0-9/+]{40})[\"']?"
        ),
    ),
    Detector(
        rule_id="github_token",
        name="GitHub Token",
        severity="high",
        pattern=re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b"),
    ),
    Detector(
        rule_id="gitlab_token",
        name="GitLab Token",
        severity="high",
        pattern=re.compile(r"\bglpat-[A-Za-z0-9\-_]{20}\b"),
    ),
    Detector(
        rule_id="slack_token",
        name="Slack Token",
        severity="high",
        pattern=re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,72}\b"),
    ),
    Detector(
        rule_id="jwt",
        name="JSON Web Token",
        severity="medium",
        pattern=re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    ),
    Detector(
        rule_id="private_key_block",
        name="Private Key Block",
        severity="critical",
        pattern=re.compile(r"-----BEGIN (?:RSA|EC|OPENSSH|DSA|PGP) ?PRIVATE KEY-----"),
    ),
    Detector(
        rule_id="generic_password",
        name="Generic Password Assignment",
        severity="medium",
        pattern=re.compile(
            r"(?i)\b(?:password|passwd|pwd)[\"']?\s*[=:]\s*[\"']?([^\s\"'][^\"'\n]{5,})[\"']?"
        ),
    ),
    Detector(
        rule_id="email",
        name="Email Address",
        severity="low",
        pattern=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ),
    Detector(
        rule_id="us_ssn",
        name="US Social Security Number",
        severity="high",
        pattern=re.compile(r"\b(\d{3})-(\d{2})-(\d{4})\b"),
        validator=_ssn_ok,
    ),
    Detector(
        rule_id="credit_card",
        name="Credit Card Number",
        severity="high",
        pattern=re.compile(r"\b(?:\d[ -]?){13,19}\b"),
        validator=_luhn_ok,
    ),
]

REGEX_DETECTORS_BY_ID = {d.rule_id: d for d in REGEX_DETECTORS}


# --- Entropy detector -------------------------------------------------------

ENTROPY_RULE_ID = "high_entropy_string"
ENTROPY_SEVERITY = "medium"

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9+/_=-]{20,}")

# Skip tokens that are extremely common, non-secret-looking high-entropy
# strings: hex git hashes, UUIDs are still flagged since they can be useful
# signal, but obvious placeholders/words are excluded by the threshold itself.


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    length = len(s)
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


def scan_line_entropy(line: str, threshold: float) -> list[Match]:
    matches = []
    for m in _TOKEN_PATTERN.finditer(line):
        token = m.group(0)
        if shannon_entropy(token) >= threshold:
            matches.append(Match(m.start(), m.end(), token))
    return matches


def all_rule_metadata() -> list[dict]:
    """Stable rule_id/name/severity for every detector, including entropy.

    Used to build the SARIF `rules` array so it's complete even on a run
    with zero findings for a given rule.
    """
    metadata = [
        {"rule_id": d.rule_id, "name": d.name, "severity": d.severity} for d in REGEX_DETECTORS
    ]
    metadata.append(
        {"rule_id": ENTROPY_RULE_ID, "name": "High Entropy String", "severity": ENTROPY_SEVERITY}
    )
    return metadata


def redact(text: str) -> str:
    """Show a short, non-sensitive preview of a matched secret."""
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}{'*' * (len(text) - 8)}{text[-4:]}"
