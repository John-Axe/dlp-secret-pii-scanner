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
