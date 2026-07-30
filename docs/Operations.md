# Operations

How to actually run and maintain this tool day to day, across its three
real distribution paths (see [`Architecture.md`](Architecture.md#deployment-diagram---the-three-ways-this-runs)
for how they relate). For diagnosing a specific failure, see
[`Troubleshooting.md`](Troubleshooting.md) instead — this document is about
routine operation, not incident response.

## Running it

### As a CLI

```bash
pip install dlp-secret-pii-scanner
dlp-scan . --fail-on high
```

For a full-repo scan in CI or a local one-off check. See
[`README.md`](../README.md#usage) for the flag reference and
[`README.md`](../README.md#6-parallel-scanning---jobs) for when `--jobs` is
worth reaching for — short version: full-repo scans benefit, a small
`--diff-only` check usually doesn't.

### As a pre-commit hook

```yaml
repos:
  - repo: https://github.com/John-Axe/dlp-secret-pii-scanner
    rev: v0.1.0
    hooks:
      - id: dlp-scan
```

Two things worth knowing that aren't obvious from the one-line config:

- `.pre-commit-hooks.yaml` declares `types: [text]` — pre-commit itself
  filters out binary files before `dlp-scan` ever sees them, a separate
  mechanism from `dlp-scan`'s own null-byte-based binary detection
  (`scanner._is_probably_binary`). Both exist; either alone would be
  sufficient, but they're not the same check.
- pre-commit invokes `dlp-scan` with the specific staged file paths as
  positional arguments, not a directory — so it's scanning exactly the
  files about to be committed, not the whole repository, on every commit.
- The hook's pinned args (`--fail-on high --format table`) are the same as
  `dlp-scan`'s own hardcoded defaults today — redundant currently, but
  explicit on purpose, so a future change to this project's own CLI
  defaults can't silently change what an already-adopted pre-commit hook
  does.

### As a GitHub Action

```yaml
- uses: John-Axe/dlp-secret-pii-scanner@v0.1.0
  with:
    path: .
    fail-on: high
```

A composite action (`action.yml`) — installs the package fresh via
`pip install "${{ github.action_path }}"` (from the repo checkout, not
PyPI) and runs `dlp-scan` with the given inputs. See
[`README.md`](../README.md#github-action) for the full inputs list.

## Upgrading

All three paths pin a version (`rev:` for pre-commit, `@v0.1.0` for the
Action, a version specifier for `pip install`) — there's no auto-update
mechanism, by design, matching this project's general preference for
explicit over implicit (see `CONTRIBUTING.md`'s framing of suppressions).
To upgrade: bump the pin, then run the new version against your own
codebase once locally before trusting it in CI — a new detector or a
stricter default could introduce findings that didn't exist under the old
pin.

**As of this writing**, `v0.1.0` is the only tagged release; everything
described in this Phase 1-4 engineering pass is still under `[Unreleased]`
in [`CHANGELOG.md`](../CHANGELOG.md) and has not shipped in a tagged
version yet. Anyone pinning `v0.1.0` today does not have `--jobs`,
`--verbose`/`--quiet`, `[tool.dlp]` config support, or the CI
lint/type/coverage gates — check the CHANGELOG's `[Unreleased]` section,
not just this document, for what's actually available in a given pin.

## Observability

- **Default output**: findings on stdout (table/JSON/SARIF per `--format`),
  nothing else — unchanged behavior for every existing user of a pinned
  version.
- **`-v`/`--verbose`**: logs the resolved scan configuration and a
  completion summary (finding count, elapsed time) to stderr. Useful for
  confirming what a CI job's `[tool.dlp]` + CLI-flag combination actually
  resolved to, without having to reason through the precedence rules by
  hand.
- **The skipped-files warning**: appears on stderr, unprompted, whenever at
  least one file was skipped (too large / binary / unreadable) — see
  [`Limitations.md`](Limitations.md#files-and-size). `-q`/`--quiet`
  suppresses this if a CI job's logs need to stay clean; nothing about
  findings output or the exit code changes either way.
- **SARIF upload**: `pr-scan.yml` and `ci.yml` both upload SARIF output to
  GitHub's Security tab, giving code-scanning-alert-level visibility
  independent of whatever a given PR's inline comments show.

## Maintenance

- **Dependabot** (`.github/dependabot.yml`) watches `pip` and
  `github-actions` weekly. Its PRs still need a human merge — nothing
  auto-merges today. A queue of unreviewed Dependabot PRs sitting open is a
  visible signal the maintenance loop isn't being closed regularly (this
  was true of this repo at one point during this engineering pass — see
  the original audit).
- **The benchmark badge and coverage badge** (`.github/badges/*.json`)
  regenerate automatically in CI's `update-badge` job on every push to
  `main` and commit themselves back if the numbers changed — never edit
  these files by hand.
- **The benchmark corpus** (`benchmark/corpus/`) is the accuracy contract.
  Adding a detector without adding a corresponding fixture and
  `labels.json` entry means the new rule ships ungraded — see
  `CONTRIBUTING.md`'s "Adding a new detector" checklist.
