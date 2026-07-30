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
- `docs/adr/0002-zero-runtime-dependencies.md` — retroactive ADR for
  `dependencies = []`, present unchanged since the project's first commit
  (`f99d4ae`). Names the concrete stdlib substitutes already in place
  (`urllib.request` over `requests`, `argparse` over `click`/`typer`,
  hand-rolled table output over `rich`, `tomllib` over a TOML library) and
  the one real cost this has: `[tool.dlp]` config support is unavailable
  on Python 3.10 (`tomllib` is 3.11+), a documented no-op rather than a
  shim.
- `docs/Troubleshooting.md` — symptom-to-fix guidance for the specific
  problems most likely to actually come up (a missed secret, `--jobs`
  making a small scan slower, `[tool.dlp]` seemingly not applying, the
  `Unknown key(s)` config error, `dlp-scan: command not found`, pre-commit
  vs. manual scan discrepancies, a `--jobs` OS-level process-creation
  error on restricted environments) rather than a generic FAQ. Completes
  Phase 4 — all six planned docs (`Limitations`, `Threat-Model`,
  `Architecture`, `Operations`, `Performance`, `Troubleshooting`) now exist.
- `docs/Performance.md` — this session's measured throughput numbers,
  framed explicitly as machine-specific rather than a portable claim; why
  the CI-gated smoke test asserts a generous ceiling instead of a
  throughput floor; and the algorithm's actual shape (every line pays the
  cost of all 10 regex detectors plus entropy tokenization,
  unconditionally — described from reading `scanner.py`/`detectors.py`,
  explicitly labeled as not a profiler-measured result). Names known
  non-optimizations (no regex pre-filtering, no `--jobs` auto-tuning, no
  cross-run caching) directly rather than leaving them to look like
  oversights.
- `docs/Operations.md` — practical running/upgrading/maintenance guidance
  for all three distribution paths, including two details not written
  down anywhere else: pre-commit's own `types: [text]` filtering runs
  *before* `dlp-scan`'s own binary detection (two independent mechanisms,
  not one), and pre-commit invokes `dlp-scan` against specific staged file
  paths, not a directory scan. Explicitly notes that `v0.1.0` is the only
  tagged release and everything in this engineering pass is still
  `[Unreleased]` — a version-pinned consumer doesn't have any of it yet.
- `docs/Architecture.md` — a component diagram of the actual module
  dependency graph (extracted with `grep` from real `from .` imports, not
  inferred from module names — confirms no circular imports), a sequence
  diagram of the real `pr-scan.yml` CI flow, and a deployment diagram of
  the three ways this tool runs (CLI, pre-commit, GitHub Action). Doesn't
  reproduce the README's existing scan-pipeline diagram (one diagram to
  keep current, not two copies to drift apart) but does document the
  release pipeline (SLSA/Sigstore/PyPI Trusted Publisher), which wasn't
  written down anywhere before this — including the caveat that the PyPI
  publish step is `continue-on-error: true` pending PyPI-side Trusted
  Publisher configuration, not a confirmed-working claim (an earlier draft
  of this file linked to a README section that doesn't actually discuss
  releases at all — caught and corrected before committing, not after).
- `docs/Threat-Model.md` — what this tool trusts (scanned-file bytes, never
  executed; the local git binary for `--diff-only`; `GITHUB_TOKEN` for
  exactly one purpose) versus what it doesn't (file content as adversarial
  input, guarded by fuzzing + a performance regression test; the GitHub
  API's response body). Verified against source while writing, not assumed
  — confirmed via `grep` that no `shell=True`/`eval`/`exec`/`pickle` exists
  anywhere in `src/dlp/`, and corrected an early draft that mis-attributed
  a redaction safeguard to the wrong module before committing.
- `docs/Limitations.md` — detection-coverage, file-size, performance, and
  ecosystem-integration limitations consolidated in one place, plus what the
  tool deliberately doesn't do (remediate, scan git history, verify a found
  credential is live). Every claim grounded in the current implementation,
  not a hedge — several were verified against actual behavior (e.g. the CI
  workflow's fail/pass gate) while writing this, not assumed.
- `-v`/`--verbose` logs the resolved scan configuration and a completion
  summary (finding count, elapsed time) to stderr; `-q`/`--quiet` suppresses
  the skipped-files stderr notice too. Neither affects stdout findings
  output or the exit code — logging only. Uses a named `dlp` logger, not the
  root logger, and never configures handlers outside the CLI entry point
  (`main()`) — the `dlp` package's modules stay safely importable as a
  library without side-effecting a consumer's own logging setup.
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
- `--jobs N` scans files across N worker processes (`--jobs 0` = all
  available CPUs; default `--jobs 1`, unchanged sequential behavior). Uses
  multiprocessing, not threading — measured empirically first: threading was
  consistently *slower* than sequential for this CPU-bound regex workload
  (GIL contention), multiprocessing measured a real 1.4-3.6x speedup.
  Confirmed end-to-end through the real CLI (~2.5x on a 3000-file corpus,
  byte-identical output to sequential). `scan_paths(..., jobs=N)` produces
  identical findings, in identical order, with identical `ScanStats`
  totals to `jobs=1` for the same input.
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
