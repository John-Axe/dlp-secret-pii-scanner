"""`dlp-scan` console entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import report, severity
from .scanner import DEFAULT_ENTROPY_THRESHOLD, scan_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dlp-scan",
        description="Scan a source tree for secrets and PII.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="Files or directories to scan (default: current directory).",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table).",
    )
    parser.add_argument(
        "--fail-on",
        choices=[*severity.ORDER, "none"],
        default="high",
        help="Exit non-zero if any finding is at or above this severity (default: high).",
    )
    parser.add_argument(
        "--no-entropy",
        action="store_true",
        help="Disable the Shannon-entropy detector.",
    )
    parser.add_argument(
        "--entropy-threshold",
        type=float,
        default=DEFAULT_ENTROPY_THRESHOLD,  # dlp-ignore: identifier, not a secret
        help=f"Entropy threshold for flagging strings (default: {DEFAULT_ENTROPY_THRESHOLD}).",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored table output.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    findings = scan_paths(
        [Path(p) for p in args.paths],
        enable_entropy=not args.no_entropy,
        entropy_threshold=args.entropy_threshold,
    )

    if args.format == "json":
        print(report.to_json(findings))
    else:
        color = not args.no_color and sys.stdout.isatty()
        print(report.to_table(findings, color=color))

    if args.fail_on == "none":
        return 0

    if any(severity.at_least(f.severity, args.fail_on) for f in findings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
