"""Output formatting for scan results: table, json, and SARIF 2.1.0."""

from __future__ import annotations

import json

from . import __version__, detectors
from .scanner import Finding

SEVERITY_COLOR = {
    "low": "\033[36m",
    "medium": "\033[33m",
    "high": "\033[31m",
    "critical": "\033[1;31m",
}
RESET = "\033[0m"

SARIF_SCHEMA_URI = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
TOOL_INFORMATION_URI = "https://github.com/John-Axe/dlp-secret-pii-scanner"

# SARIF result levels are "none", "note", "warning", "error".
SEVERITY_TO_SARIF_LEVEL = {
    "low": "note",
    "medium": "warning",
    "high": "error",
    "critical": "error",
}


def to_json(findings: list[Finding]) -> str:
    return json.dumps([f.to_dict() for f in findings], indent=2)


def to_sarif(findings: list[Finding]) -> str:
    """Render findings as a SARIF 2.1.0 log, suitable for
    github/codeql-action/upload-sarif and the Security > Code scanning tab.
    """
    rules = [
        {
            "id": rule["rule_id"],
            "name": rule["name"],
            "shortDescription": {"text": rule["name"]},
            "defaultConfiguration": {"level": SEVERITY_TO_SARIF_LEVEL[rule["severity"]]},
            "properties": {"security-severity": _security_severity_score(rule["severity"])},
        }
        for rule in detectors.all_rule_metadata()
    ]

    results = [
        {
            "ruleId": f.rule_id,
            "level": SEVERITY_TO_SARIF_LEVEL[f.severity],
            "message": {"text": f"{f.rule_name} detected: {f.redacted}"},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": f.file},
                        "region": {"startLine": f.line, "startColumn": f.column},
                    }
                }
            ],
            "partialFingerprints": {"dlpFingerprint/v1": f.fingerprint},
        }
        for f in findings
    ]

    sarif = {
        "$schema": SARIF_SCHEMA_URI,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "dlp-secret-pii-scanner",
                        "informationUri": TOOL_INFORMATION_URI,
                        "version": __version__,
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(sarif, indent=2)


def _security_severity_score(severity: str) -> str:
    """Maps our severity scale to the 0-10 score GitHub's Security tab uses
    to bucket findings into its own Critical/High/Medium/Low display."""
    return {"low": "3.0", "medium": "5.0", "high": "7.5", "critical": "9.5"}[severity]


def to_table(findings: list[Finding], *, color: bool = False) -> str:
    if not findings:
        return "No findings."

    headers = ["SEVERITY", "RULE", "FILE", "LINE:COL", "PREVIEW"]
    rows = [
        [
            f.severity.upper(),
            f.rule_id,
            f.file,
            f"{f.line}:{f.column}",
            f.redacted,
        ]
        for f in findings
    ]
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

    def fmt_row(cells: list[str]) -> str:
        return "  ".join(cell.ljust(width) for cell, width in zip(cells, widths))

    lines = [fmt_row(headers), fmt_row(["-" * w for w in widths])]
    for f, row in zip(findings, rows):
        line = fmt_row(row)
        if color:
            c = SEVERITY_COLOR.get(f.severity, "")
            line = f"{c}{line}{RESET}"
        lines.append(line)
    lines.append(f"\n{len(findings)} finding(s).")
    return "\n".join(lines)
