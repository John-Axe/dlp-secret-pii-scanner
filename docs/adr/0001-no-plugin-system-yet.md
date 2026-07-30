# 0001 — Detectors stay a hardcoded list; no plugin system yet

## Status

Accepted (2026-07-30)

## Context

`src/dlp/detectors.py` defines all 11 detection rules as a module-level
Python list, `REGEX_DETECTORS`. There is no discovery mechanism, entry-point
system, or external-rule-loading path — adding, removing, or changing a rule
means editing this file directly and shipping a new release.

This is the one place in an otherwise deliberately low-coupling, high-cohesion
codebase (10 single-responsibility modules, no circular imports, no
duplicated logic — see the engineering audit that prompted this ADR) where
extensibility is closed off by construction rather than by design. Left
unexplained, that reads to a reviewer as an oversight rather than a choice.

## Problem

Should `dlp-secret-pii-scanner` grow a plugin or entry-point mechanism so
users can register custom detectors — an org-specific internal-token format,
a proprietary secret pattern — without forking the project or waiting on a
release?

## Alternatives considered

**A. Python entry points** (`importlib.metadata.entry_points`, the mechanism
`pytest` and `flake8` plugins use). A third party publishes a package
declaring a `dlp.detectors` entry point; this tool discovers and loads it at
runtime.

- Cost: a real plugin ABI has to be versioned and kept stable independently
  of the tool's own release cadence — a breaking change to `Detector`'s
  shape (its `rule_id`/`severity`/`pattern`/`validator` fields) becomes a
  breaking change for every published plugin, not just this repo. Needs
  documentation, a discovery/loading code path, and — since this project's
  central claim is a CI-enforced accuracy benchmark, not just detection —
  some story for whether third-party rules are graded by that benchmark at
  all, given they're not in this repo's own `benchmark/corpus/`.
- Trust boundary: this tool runs against real source trees in CI, often with
  `contents: read` and sometimes `security-events: write` permissions (see
  `pr-scan.yml`). A plugin system means arbitrary third-party Python code
  executes in that same CI job. That's a materially larger attack surface
  than a regex list reviewed in this repo's own PRs — worth naming
  explicitly, not glossing over.

**B. Config-file-defined custom regex rules** (e.g. a `custom_rules` array
in `[tool.dlp]`, à la `detect-secrets`' plugin config or gitleaks' custom
rules in `.gitleaks.toml`). Lower-risk than (A) — no arbitrary code
execution, just data (a regex + metadata) — but still real scope: a second
rule-authoring surface to validate, document, and keep benchmark-honest
alongside the built-in one.

**C. Status quo — hardcoded list, PR to add a rule.** Zero new
infrastructure. Every rule that exists has been reviewed in this repo,
benchmarked against `benchmark/corpus/`, and ships with the same CI
guarantees as everything else. Cost falls on whoever wants a new rule: open
a PR (see `CONTRIBUTING.md`'s "Adding a new detector" checklist) and wait
for a release, rather than registering a plugin locally.

## Decision

**Stay with (C) for now.** Concretely:

- `REGEX_DETECTORS` remains a hardcoded list in `detectors.py`.
- No entry-point discovery, no custom-rule config key is added in this
  pass.

This is a scope decision grounded in the actual size and stability of the
rule set, not a guess: `git log --follow -- src/dlp/detectors.py` shows all
11 detectors were added in a single commit at project inception
(`f99d4ae`), and every commit touching the file since has been a fix or
refactor — zero new detector rules have shipped since day one. A plugin
system solves a scaling problem this project doesn't currently have, at the
cost of a genuinely larger trust boundary (option A) or a second
rule-authoring/validation surface (option B) that has to be maintained
whether or not anyone uses it.

## Consequences

- Adding rule #12 still means a PR to this repo, following
  `CONTRIBUTING.md`'s checklist (rule + benchmark fixture + label entry +
  tests + README line) — by design, so every rule keeps the same accuracy
  guarantee.
- An org with a genuinely private, sensitive-format secret (e.g. an internal
  API key format that can't be described in a public PR) has no first-class
  way to add it without forking. The nearest workaround today is the
  existing entropy detector plus `.dlpignore`/`# dlp-ignore` for the
  inverse case — not a real substitute, and worth being honest about as a
  named limitation (tracked for `docs/Limitations.md`, Phase 4) rather than
  silently unaddressed.
- This decision is revisitable, not permanent. The trigger for revisiting
  it isn't a fixed timeline — it's evidence: multiple real requests for
  org-private rules, or the rule count actually starting to grow the way it
  hasn't in this project's history so far. If that happens, option B
  (config-defined regex rules) is the better starting point of the two
  alternatives — it doesn't introduce arbitrary code execution into a CI
  job the way option A does, which is the harder cost to walk back later.

## Tradeoffs

|  | Chosen (C, hardcoded) | A (entry points) | B (config regex) |
|---|---|---|---|
| New rule cost | PR + release | Publish a plugin package | Edit a config file |
| CI trust boundary | Unchanged | Third-party code executes in CI | Unchanged (data, not code) |
| Accuracy guarantee | Every rule benchmarked | Not guaranteed for third-party rules | Not guaranteed, but lower-risk to add later |
| Infrastructure cost now | None | Real (versioned ABI, docs, discovery) | Real (schema, validation, docs) |
| Fits current rule-count trend (0 additions since inception) | Yes | No — solves a scale problem that hasn't materialized | Partial |
