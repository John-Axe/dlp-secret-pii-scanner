"""`dlp-scan` console entry point."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from . import __version__, baseline, config, diff, report, severity
from .scanner import DEFAULT_ENTROPY_THRESHOLD, ScanStats, scan_paths
from .shared_finding import write_shared_findings_jsonl

# A named, not root, logger - a library (which dlp's own modules are meant
# to be importable as, see docs/adr/0001) must never configure logging
# handlers at import time, only an application/CLI entry point may. This
# module IS that entry point; scanner.py/detectors.py/etc. never touch
# logging at all, by design.
LOGGER = logging.getLogger("dlp")

# Hardcoded fallback for each config-eligible flag, used only when neither
# the CLI nor pyproject.toml's [tool.dlp] supplied a value. Kept as one
# table so build_parser()'s --help text and main()'s resolution both read
# from the same source of truth instead of two places that could drift.
_DEFAULTS = {
    "format": "table",
    "fail_on": "high",
    "no_entropy": False,
    "entropy_threshold": DEFAULT_ENTROPY_THRESHOLD,
    "no_color": False,
    "base_ref": "origin/main",
}

EPILOG = """\
examples:
  dlp-scan .                                        # scan cwd, table output, fail on high+
  dlp-scan src/ --fail-on critical                   # only fail on critical findings
  dlp-scan . --format sarif --fail-on none > r.sarif # SARIF for the Security tab
  dlp-scan . --write-baseline .dlp-baseline.json     # snapshot current findings
  dlp-scan --diff-only --base-ref origin/main \\
    --baseline .dlp-baseline.json --fail-on high     # only new findings can fail a PR
  dlp-scan . --jobs 0 -v                             # parallel scan, log config + timing

exit codes:
  0  no finding met --fail-on (or --fail-on none)
  1  at least one non-baselined finding met or exceeded --fail-on

config file:
  Per-project defaults for --format/--fail-on/--no-entropy/--entropy-threshold/
  --no-color/--base-ref can live in pyproject.toml instead of being repeated on
  every invocation:

    [tool.dlp]
    fail_on = "critical"
    entropy_threshold = 4.5

  A CLI flag always overrides the config file. --no-config ignores it entirely.
"""


def _configure_logging(*, verbosity: int, quiet: bool) -> None:
    """Wires a stderr handler with a level driven by -v/-q.

    Default (neither flag) is WARNING - unchanged from before --verbose/
    --quiet existed, since the only thing that ever logged before this was
    the stderr skip-summary (see main()), which is warning-severity by
    nature: something didn't get scanned. -q raises the bar to ERROR
    (silences the skip-summary too); each -v lowers it, INFO then DEBUG.
    Idempotent - safe to call more than once (e.g. across tests in the same
    process) since it clears any handler it previously added rather than
    accumulating duplicates.
    """
    if quiet:
        level = logging.ERROR
    elif verbosity >= 2:
        level = logging.DEBUG
    elif verbosity == 1:
        level = logging.INFO
    else:
        level = logging.WARNING

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("dlp-scan: %(message)s"))
    LOGGER.handlers.clear()
    LOGGER.addHandler(handler)
    LOGGER.setLevel(level)
    LOGGER.propagate = False  # don't also hand records to the root logger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dlp-scan",
        description="Scan a source tree for secrets and PII.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="Files or directories to scan (default: current directory).",
    )
    # These six flags default to None, not their real fallback value: None
    # means "not explicitly passed on the command line," which main() needs
    # to distinguish from an explicit choice, so pyproject.toml's
    # [tool.dlp] table can fill in a default without a CLI flag looking
    # like it was already given. See _DEFAULTS/_resolve_settings below.
    parser.add_argument(
        "--format",
        choices=["table", "json", "sarif"],
        default=None,
        help=f"Output format (default: {_DEFAULTS['format']}).",
    )
    parser.add_argument(
        "--fail-on",
        choices=[*severity.ORDER, "none"],
        default=None,
        help=f"Exit non-zero if any finding is at or above this severity "
        f"(default: {_DEFAULTS['fail_on']}).",
    )
    parser.add_argument(
        "--no-entropy",
        action="store_true",
        default=None,
        help="Disable the Shannon-entropy detector.",
    )
    parser.add_argument(
        "--entropy-threshold",
        type=float,
        default=None,
        help=f"Entropy threshold for flagging strings "
        f"(default: {DEFAULT_ENTROPY_THRESHOLD}).",  # dlp-ignore: identifier, not a secret
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        default=None,
        help="Disable colored table output.",
    )
    parser.add_argument(
        "--diff-only",
        action="store_true",
        help="Scan only files changed vs --base-ref (via git diff) instead of --paths.",
    )
    parser.add_argument(
        "--base-ref",
        default=None,
        help=f"Git ref to diff against when --diff-only is set (default: {_DEFAULTS['base_ref']}).",
    )
    parser.add_argument(
        "--no-config",
        action="store_true",
        help="Ignore pyproject.toml's [tool.dlp] table entirely, even if present.",
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
    parser.add_argument(
        "--emit-findings",
        type=Path,
        default=None,
        help="Also write findings.jsonl (shared ecosystem finding schema) to this path, "
        "for observability-stack's Promtail to tail. Overwritten each run.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Scan files in parallel using this many worker processes (0 = all "
        "available CPUs). Default: 1 (sequential) - not config-file-eligible, "
        "since this is a per-run/per-machine tradeoff, not a team standard. "
        "Output is identical to sequential for the same input; only wall-clock "
        "time differs. Mainly worth it for a full-repo scan, not a small "
        "--diff-only PR check where process-pool startup cost dominates.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Log the resolved scan configuration and a completion summary to "
        "stderr. Repeat for more detail (-vv).",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress the stderr skipped-files notice. Findings output (stdout) and "
        "the exit code are never affected by this flag, only stderr logging.",
    )
    return parser


def _resolve_settings(args: argparse.Namespace, cfg: dict[str, Any]) -> dict[str, Any]:
    """Merges CLI args over pyproject.toml's [tool.dlp] table over the
    hardcoded fallback, in that priority order. An arg is only "not
    explicitly passed" (falls through to config) when it's None - see
    build_parser()'s comment on why these six flags default to None
    instead of their real fallback value.
    """
    resolved = {}
    for key, fallback in _DEFAULTS.items():
        cli_value = getattr(args, key)
        resolved[key] = cli_value if cli_value is not None else cfg.get(key, fallback)
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(verbosity=args.verbose, quiet=args.quiet)
    start_time = time.perf_counter()

    try:
        cfg = {} if args.no_config else config.load_config()
    except ValueError as exc:
        LOGGER.error(str(exc))
        return 1
    settings = _resolve_settings(args, cfg)
    jobs = (os.cpu_count() or 1) if args.jobs <= 0 else args.jobs

    LOGGER.info(
        "format=%s fail_on=%s entropy_threshold=%s jobs=%d%s",
        settings["format"],
        settings["fail_on"],
        settings["entropy_threshold"],
        jobs,
        " (config file loaded)" if cfg else "",
    )

    stats = ScanStats()

    if args.diff_only:
        changed = diff.changed_files(settings["base_ref"], Path.cwd())
        findings = (
            scan_paths(
                changed,
                enable_entropy=not settings["no_entropy"],
                entropy_threshold=settings["entropy_threshold"],
                ignore_root=Path.cwd(),
                stats=stats,
                jobs=jobs,
            )
            if changed
            else []
        )
    else:
        findings = scan_paths(
            [Path(p) for p in args.paths],
            enable_entropy=not settings["no_entropy"],
            entropy_threshold=settings["entropy_threshold"],
            stats=stats,
            jobs=jobs,
        )

    if stats.total_skipped:
        # WARNING, not INFO: shown by default (unless -q), deliberately, and
        # only when something was actually skipped - a summary on every
        # ordinary run (the common case, zero skips) would just be noise CI
        # logs don't need. This is specifically about making a *skip*
        # visible, not general scan telemetry - see the engineering audit
        # for why a silent skip (a >5MB file, an unreadable file) matters
        # for a tool whose job is finding things that shouldn't be missed.
        LOGGER.warning(
            "%d file(s) skipped and NOT scanned (%d too large, %d binary, "
            "%d unreadable) -- %d file(s) scanned successfully",
            stats.total_skipped,
            stats.files_skipped_too_large,
            stats.files_skipped_binary,
            stats.files_skipped_unreadable,
            stats.files_scanned,
        )

    LOGGER.info(
        "scan complete: %d finding(s) in %.2fs", len(findings), time.perf_counter() - start_time
    )

    if args.write_baseline:
        baseline.write_baseline(args.write_baseline, findings)
        print(f"Wrote {len({f.fingerprint for f in findings})} fingerprint(s) to {args.write_baseline}")
        return 0

    if args.baseline:
        known = baseline.load_baseline(args.baseline)
        findings = baseline.filter_known(findings, known)

    if args.emit_findings:
        write_shared_findings_jsonl(findings, args.emit_findings)

    if settings["format"] == "json":
        print(report.to_json(findings))
    elif settings["format"] == "sarif":
        print(report.to_sarif(findings))
    else:
        color = not settings["no_color"] and sys.stdout.isatty()
        print(report.to_table(findings, color=color))

    if settings["fail_on"] == "none":
        return 0

    if any(severity.at_least(f.severity, settings["fail_on"]) for f in findings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
