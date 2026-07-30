# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/).

This file is backfilled as of 2026-07-30 from `git log`; entries above that date
were written from the commit history rather than at commit time, so wording is
summarized rather than verbatim. Every entry from this point forward should be
added in the same PR as the change it describes.

## [Unreleased]

### Added
- `docs/adr/` — Architecture Decision Records, starting with
  [0001](docs/adr/0001-no-plugin-system-yet.md): why detectors stay a
  hardcoded list rather than growing a plugin/entry-point system, grounded
  in this project's actual detector-addition history (zero new rules since
  the initial commit) rather than a guess.
- `benchmark/run_throughput_benchmark.py` measures files/sec and MB/sec
  against a synthetic, on-the-fly-generated corpus (not CI-gated — wall-clock
  throughput is machine-dependent in a way the accuracy benchmark isn't).
  `tests/test_performance_smoke.py` carries the actual CI-gated regression
  guard: generous bounds meant to catch a future catastrophic regression
  (e.g. a detector regex that starts backtracking exponentially), not to
  enforce a specific throughput number — closes a gap the original
  engineering audit named explicitly.
- `findings.jsonl` output via `--emit-findings`, mapping this tool's findings onto
  the ecosystem-wide shared finding schema (severity, MITRE ATT&CK, OWASP fields)
  for consumption by `observability-stack`'s Promtail/Loki/Grafana pipeline.
- `CONTRIBUTING.md` — the pre-PR check sequence, the detector-addition checklist,
  and the existing suppression conventions, previously undocumented outside the
  maintainer's own head.
- This `CHANGELOG.md`.
- `--version` flag and `python -m dlp` as an alternative entry point alongside the
  `dlp-scan` console script.
- Worked examples and exit-code documentation in `dlp-scan --help`'s epilog,
  previously only in the README.
- Three structured issue forms (false positive, new detector request, bug report),
  a PR template mirroring the CONTRIBUTING.md pre-PR checklist, and `CODEOWNERS`.
- CI now runs `ruff check` and `mypy src/` (strict) as required gates, and the test
  job enforces a 90% coverage floor (`pytest-cov`) with `--cov-report=term-missing`
  surfacing exactly which lines aren't. `src/dlp/py.typed` (PEP 561) is added so
  downstream consumers of the published package get type-checking benefit from it
  too, not just this repo's own CI.
- `scripts/coverage_badge.py` generates a shields.io coverage badge from a
  `coverage json` report the same way `benchmark/run_benchmark.py` already
  generates the precision/recall badge — CI regenerates and commits both on every
  push to `main` if they changed.
- `dlp-scan` now reports skipped files on stderr (count and reason: too large /
  binary / unreadable) whenever at least one file was skipped, instead of
  silently producing the same empty result a clean scan would.
- `dlp.github_pr` now caps inline PR comments at 25 by default (`--max-comments`,
  highest-severity findings kept when over the cap) and retries a detected
  GitHub rate limit (429, or a 403 carrying `Retry-After`/exhausted
  `X-RateLimit-Remaining`) with GitHub-directed backoff, up to 3 attempts.
- Property-based tests (`hypothesis`) for the Luhn credit-card validator, the
  SSN validator, and Shannon entropy — generated inputs alongside the existing
  hand-picked examples, covering invariants like "any single-digit corruption
  of a valid card number is always rejected" and "entropy is invariant under
  shuffling" that example-based tests don't naturally reach.
- `pyproject.toml`'s `[tool.dlp]` table can now supply per-project defaults for
  `--format`/`--fail-on`/`--no-entropy`/`--entropy-threshold`/`--no-color`/
  `--base-ref`, so a team doesn't have to repeat CLI flags on every invocation.
  CLI flags always win; `--no-config` opts out entirely. Uses stdlib `tomllib`
  (3.11+) rather than a new runtime dependency — a documented no-op, not a
  crash, on Python 3.10.

### Fixed
- Two silent-failure paths in `scan_file` — a file over 5MB and a file that
  raised `OSError` on read (permission denied, or removed mid-scan) — both
  previously returned `[]` indistinguishably from "scanned, no findings."
  Both are now counted and surfaced (see Added, above).
- `dlp.github_pr.post_review_comments` previously had no bound on how many
  sequential requests it would fire for a single PR, and any non-422 HTTP
  error (including a transient rate limit) propagated as an unhandled
  traceback with no partial-progress information. Now bounded and
  rate-limit-aware (see Added, above); a genuine permissions error (a bare
  403) still raises immediately rather than being retried into a slower,
  more confusing failure.
- `DEFAULT_SKIP_DIRS` didn't include `.hypothesis` or `.ruff_cache` — adopting
  either tool caused `dlp-scan .` to walk into their cache internals and flag
  cached bytes as high-entropy findings (discovered by this repo self-scanning
  itself right after adopting `hypothesis`). Fixed at the source in `scanner.py`
  so this doesn't recur for any project that adopts either tool, not just this one.

### Changed
- Code-smell cleanup across `src/` and `tests/` (refactor, no behavior change).

### Fixed
- Security, efficiency, and correctness fixes across the scanner.
- `fuzz/fuzz_scanner.py` now loads via `importlib.util.spec_from_file_location` in
  the smoke test rather than a path-relative import, fixing test discovery outside
  the fuzz target's own directory.
- Gitleaks false positives suppressed in both git history and the benchmark
  corpus (the corpus is deliberately full of realistic-looking fake secrets to
  test detector accuracy — see `.github/secret_scanning.yml`).

### Security
- All pip installs pinned to resolve OpenSSF Scorecard's Pinned-Dependencies check.

## [0.1.0] - 2026-06-26

Initial tagged release.

### Added
- Core CLI (`dlp-scan`): regex detectors for AWS keys, GitHub/GitLab/Slack tokens,
  JWTs, private key blocks, generic password assignments, emails, SSNs (validity-
  checked), credit cards (Luhn-validated), plus a Shannon-entropy detector for
  secrets the regexes miss.
- `.dlpignore` (path-level) and inline `# dlp-ignore` (line-level) suppression.
- Pre-commit hook (`.pre-commit-hooks.yaml`) and GitHub Action (`action.yml`)
  distribution alongside the CLI.
- Labeled precision/recall benchmark (`benchmark/`) as a CI-enforced accuracy
  gate, not a one-time claim.
- SARIF 2.1.0 output (`--format sarif`) wired to GitHub's Security tab.
- Inline PR review comments via the built-in `GITHUB_TOKEN` (`dlp.github_pr`),
  no external secret required.
- `--diff-only` scanning (only files changed vs. `--base-ref`) and `--baseline`
  fingerprint suppression, so only newly introduced findings fail a PR.
- Auto-updating benchmark badge, regenerated and committed by CI on every push
  to `main`.
- Fuzz target (`fuzz/fuzz_scanner.py`, atheris) exercising the detection layer.
- SLSA provenance hashes, Sigstore keyless artifact signing, and PyPI publish via
  OIDC Trusted Publisher on tagged releases (`.github/workflows/release.yml`).
- `SECURITY.md` with a private vulnerability-reporting process.
- CodeQL, OpenSSF Scorecard, and gitleaks workflows.

### Security
- Every third-party GitHub Action pinned to a full commit SHA.
- Least-privilege `permissions:` blocks on every CI job.
- Benchmark corpus (deliberately seeded with realistic fake secrets) excluded
  from GitHub secret scanning to avoid false alarms on test fixtures.

[Unreleased]: https://github.com/John-Axe/dlp-secret-pii-scanner/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/John-Axe/dlp-secret-pii-scanner/releases/tag/v0.1.0
