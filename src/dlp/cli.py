"""`dlp-scan` console entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import baseline, diff, report, severity
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
        choices=["table", "json", "sarif"],
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
    parser.add_argument(
        "--diff-only",
        action="store_true",
        help="Scan only files changed vs --base-ref (via git diff) instead of --paths.",
    )
    parser.add_argument(
        "--base-ref",
        default="origin/main",
        help="Git ref to diff against when --diff-only is set (default: origin/main).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Baseline file of known-finding fingerprints; matching findings are "
        "excluded from output and from --fail-on, so only new findings fail the build.",
    )
    parser.add_argument(
        "--write-baseline",
        type=Path,
        default=None,
        help="Write the current findings to a baseline file (as fingerprints) and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.diff_only:
        changed = diff.changed_files(args.base_ref, Path.cwd())
        findings = (
            scan_paths(
                changed,
                enable_entropy=not args.no_entropy,
                entropy_threshold=args.entropy_threshold,
                ignore_root=Path.cwd(),
            )
            if changed
            else []
        )
    else:
        findings = scan_paths(
            [Path(p) for p in args.paths],
            enable_entropy=not args.no_entropy,
            entropy_threshold=args.entropy_threshold,
        )

    if args.write_baseline:
        baseline.write_baseline(args.write_baseline, findings)
        print(f"Wrote {len({f.fingerprint for f in findings})} fingerprint(s) to {args.write_baseline}")
        return 0

    if args.baseline:
        known = baseline.load_baseline(args.baseline)
        findings = baseline.filter_known(findings, known)

    if args.format == "json":
        print(report.to_json(findings))
    elif args.format == "sarif":
        print(report.to_sarif(findings))
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
