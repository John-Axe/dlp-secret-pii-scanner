# 0002 — Zero runtime dependencies

## Status

Accepted (2026-07-30, retroactive — the decision itself dates to project
inception)

## Context

`pyproject.toml` declares `dependencies = []`. `git log --follow -p --
pyproject.toml` shows this line was present in the very first commit
(`f99d4ae`) and has never changed since — every later commit that touched
`pyproject.toml` added to `[project.optional-dependencies] dev` (pytest,
pytest-cov, hypothesis, atheris, ruff, mypy) or `[tool.*]` config, never to
`dependencies`. This wasn't a target reached by pruning; it's a constraint
the codebase has been written against from day one, and several real design
choices only make sense in light of it. Left unexplained, a reviewer
skimming `src/dlp/` might read `urllib.request` instead of `requests`, or
`argparse` instead of `click`, as an oversight rather than a deliberate
constraint.

## Problem

Should `dlp-secret-pii-scanner` take on runtime dependencies — an HTTP
client, a CLI framework, a TOML parser, a terminal-formatting library — the
way most comparable tools do, in exchange for less code to maintain
in-repo?

## Alternatives considered

**A. Take on conventional runtime dependencies.** `requests` for
`github_pr.py`'s GitHub API calls, `click` or `typer` for `cli.py`, `rich`
for table/colored output, a TOML library (`tomli`/`toml`) for
`[tool.dlp]` config support on Python <3.11. This is what most CLI security
tools do, and each library is individually well-maintained and low-risk.

- Cost: this tool installs into two places with a materially higher trust
  bar than a typical app dependency tree — a pre-commit hook
  (`.pre-commit-hooks.yaml`, `language: python`, a fresh venv built and
  `pip install`ed on every hook-repo update) and a GitHub Action
  (`action.yml`, `pip install` into the runner, running with `contents:
  read` and sometimes `pull-requests`/`security-events: write`
  permissions in `pr-scan.yml`). Every runtime dependency added is a
  package whose maintainers, release process, and transitive dependencies
  become part of that trust boundary — see `docs/Threat-Model.md`'s
  Supply Chain section. `docs/adr/0001-no-plugin-system-yet.md` already
  named this exact tradeoff for a hypothetical plugin ABI; the same
  argument applies to any added runtime dependency, not just plugins.
- Concretely, each candidate has a stdlib substitute this project already
  uses instead: `urllib.request`/`urllib.error` in `github_pr.py` (not
  `requests`), `argparse` in `cli.py` (not `click`/`typer`), hand-rolled
  table formatting in `report.py` (not `rich`), and `tomllib` in
  `config.py` (not `tomli`).

**B. Zero runtime dependencies, stdlib only.** Every capability the tool
needs — HTTP calls, CLI parsing, TOML parsing, colored/tabular terminal
output — is built on what ships with CPython. The cost lands as slightly
more in-repo code (`github_pr.py`'s own retry/rate-limit handling instead
of a library's, `report.py`'s own table renderer) in exchange for nothing
external to audit, pin, or have compromised upstream.

## Decision

**Stay with (B).** Concretely:

- `dependencies = []` in `pyproject.toml`, unchanged since project
  inception.
- HTTP: `urllib.request`/`urllib.error` (`github_pr.py`).
- CLI parsing: `argparse` (`cli.py`).
- TOML config: stdlib `tomllib`, Python 3.11+ only. On the still-supported
  3.10 floor, `config.py` treats a missing `tomllib` as "no `[tool.dlp]`
  config" — a documented no-op (see `README.md`'s config section and
  `CHANGELOG.md`), not a crash, and not worth adding a runtime dependency
  to close for one minor Python version. This is the sharpest real
  tradeoff (B) has actually cost so far: a capability (`[tool.dlp]`
  support) that's simply unavailable on 3.10 rather than shimmed.
- Ecosystem interop (`shared_finding.py`, the shared finding schema) is
  built to require nothing new either — its own docstring states this
  explicitly: "Deliberately has zero new runtime dependency... Anyone who
  wants strict validation against the schema can install
  `finding-schema`... this module doesn't require it."
- Dev-only tooling (`pytest`, `pytest-cov`, `hypothesis`, `atheris`,
  `ruff`, `mypy`) is exempt — it never ships in the installed package and
  never runs in a scanned repo's environment, only in this repo's own CI
  and local development.

## Consequences

- `pip install dlp-secret-pii-scanner` (or the pre-commit hook's venv
  build, or the GitHub Action's `pip install`) resolves instantly — no
  dependency graph to solve, no version conflicts possible with whatever
  the installing repo already pins.
- `github_pr.py` owns its own bounded retry/backoff/rate-limit handling
  (see the fix in commit `c9cd3c4`) instead of inheriting a
  battle-tested implementation from `requests`/`urllib3` — more code to
  keep correct in this repo, in exchange for one fewer package in the
  supply chain of something that runs with GitHub API write scope.
- `report.py`'s table formatting is hand-rolled rather than delegated to
  `rich`/`tabulate` — less visually polished, easier to audit.
- A real capability gap exists on Python 3.10: `[tool.dlp]` config support
  requires 3.11+ (`tomllib`). This is accepted and documented rather than
  closed with a dependency, but it is a genuine, named limitation, not a
  free lunch.
- This decision is revisitable the same way ADR 0001 is: not on a
  timeline, but on evidence — if a stdlib substitute turns out to be
  meaningfully wrong (a `urllib`-based retry bug a `requests`-based
  implementation wouldn't have had, for instance), that's the kind of
  concrete cost that would justify reopening this, not a general
  preference for using established libraries.

## Tradeoffs

|  | Chosen (B, zero deps) | A (conventional deps) |
|---|---|---|
| Install/build trust surface (pre-commit hook, GitHub Action) | Nothing external to audit | Every dependency's maintainers/releases/transitives |
| In-repo code to maintain | More (retry logic, table rendering, arg parsing all hand-rolled) | Less |
| `[tool.dlp]` on Python 3.10 | Unsupported, documented no-op | Would work with a TOML library |
| Install speed / conflict risk | Instant, no resolution | Normal dependency resolution, possible conflicts with host repo's pins |
| Battle-tested edge cases (HTTP retries, CLI parsing) | Only as good as this repo's own tests | Inherited from widely-used libraries |
