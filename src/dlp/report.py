"""Output formatting for scan results: json and table."""

from __future__ import annotations

import json

from .scanner import Finding

SEVERITY_COLOR = {
    "low": "\033[36m",
    "medium": "\033[33m",
    "high": "\033[31m",
    "critical": "\033[1;31m",
}
RESET = "\033[0m"


def to_json(findings: list[Finding]) -> str:
    return json.dumps([f.to_dict() for f in findings], indent=2)


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
