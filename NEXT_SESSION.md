# Handoff — engineering transformation, Phase 8 complete

**Last updated:** 2026-07-30, Phase 8 complete.
**Read this file first** if you're picking this work up cold — it should let
you continue without re-deriving anything below.

## What this is

`dlp-secret-pii-scanner` went through a structured engineering-quality
pass: audit → 5-phase roadmap → incremental, individually-verified PRs, each
with its own Goal/Reasoning/Tradeoffs writeup in its commit message. Three
more phases were added mid-pass (see "How Phases 6-8 came about" below).
Nothing has been pushed to `origin` or merged — everything lives on eight
stacked local branches, one commit per coherent change. `docs/Roadmap.md`
has the phase-by-phase breakdown for Phases 1-5 with commit references (not
yet updated for Phases 6-8 — a reasonable next edit if continuing); this
file stays focused on handoff state.

## Completed work

### Phases 1-5 (see [`docs/Roadmap.md`](docs/Roadmap.md) for the full commit-by-commit breakdown)

CI gates, five real code bugs found and fixed, `--jobs`/logging, four ADRs
(`docs/adr/0001`-`0004`), six production-readiness docs, `Roadmap.md`/`FAQ.md`.

### Phase 6 — Deepen engineering documentation (`engineering-audit/phase-6-detector-and-methodology-docs`, 3 commits)

`docs/Detectors.md` (per-detector reference), `docs/Benchmark-Methodology.md`
(v1), `CONTRIBUTING.md` Testing philosophy section. Writing `Detectors.md`
surfaced three real detector coverage gaps, verified against vendor docs.

### Phase 7 — Detector coverage fixes (`engineering-audit/phase-7-detector-coverage-fixes`, 6 commits)

Fixed all three gaps Phase 6 found (`aws_access_key_id` narrowed to real
credential prefixes, `github_token` gained `github_pat_` support,
`private_key_block` gained PKCS#8 support — precision climbed 94.44% →
95.00% across the three, zero regressions). Also found and fixed, on
explicit human confirmation, a real unrelated bug: `README.md`'s
documented `<!-- dlp-ignore -->` HTML-comment suppression style never
actually worked (`ignore._INLINE_IGNORE_RE` required a literal `#`/`//`);
widened the regex, confirmed working end-to-end.

### Phase 8 — Benchmark, testing methodology, and evidence hardening (`engineering-audit/phase-8-benchmark-hardening`, 7 commits) — **COMPLETE**

1. `83007bb` — 4 new negative fixtures (false-positive traps: token-prefix
   mentions, boundary-length near-misses, PKCS#8 public key, JSON env
   placeholders)
2. `8db1b27` — 9 new positive fixtures (2nd example for every rule that had
   exactly one, plus unicode/multi-secret/CRLF edge cases)
3. `8abbf1c` — sample-size (**N**) column + match-level diagnostics section
   in `run_benchmark.py`, purely additive, existing pass/fail contract
   unchanged
4. `60f56a9` — peak RSS measurement in `run_throughput_benchmark.py`
   (stdlib `resource`, POSIX-only, degrades gracefully on Windows)
5. `29dbedf` — **fixed real stale-data drift found while auditing**:
   `.github/badges/benchmark.json` and `README.md`'s table still said 94%
   precision / 17 TP from before Phase 7, because nothing regenerates the
   badge except a `main`-branch push that's never happened. Regenerated
   both; added `test_committed_badge_matches_fresh_run` so `pytest` catches
   this specific drift on every run going forward
6. `811a17a` — strengthened `docs/Benchmark-Methodology.md` (plain-English
   primer, fixture-category breakdown, Reproducibility section, Threats to
   validity section) and, while doing so, **found the same stale number
   repeated in three more places** (README's intro line, `Detectors.md`,
   two spots in `FAQ.md` — one of which had overclaimed that drift was
   structurally impossible, which had just been proven false); fixed all,
   replaced hardcoded numbers with pointers to the authoritative source
   where possible so they can't drift silently again
7. `595ab7a` — documented the badge-drift test as a distinct testing
   category in `CONTRIBUTING.md` (it checks artifact staleness, not
   detector correctness — doesn't fit the existing five categories)

**Final state**: every corpus rule now has ≥2 true positives (was as low
as 1 for six rules). Benchmark: 97.14% precision, 100% recall, 34 TP / 1 FP
(same single known FP as always — the entropy detector's binary-asset
case), 0 FN. 35 corpus files (23 positive, 12 negative), 229 tests, 97.46%
coverage. Every commit gate-checked (ruff, mypy, pytest+coverage,
benchmark, self-scan) before committing; every new fixture verified with a
direct `dlp-scan` run before its `labels.json` entry was written, not
assumed.

**How Phases 6-8 came about**: a mid-session message asked for a
platform-scale rebuild (Docker, REST API, plugin architecture, ML, IDE
extension) that contradicted committed ADRs — flagged, not acted on. A
follow-up exchange clarified the actual intent (deepen quality, don't
expand scope), producing Phase 6. Phase 7 followed from a one-word "fix"
of Phase 6's findings. Phase 8 followed from a further request to
strengthen the benchmark/testing methodology specifically, with an
explicit first principle (no scope change, preserve every ADR) — planned
against a real audit of `run_benchmark.py`, the corpus, and
`Benchmark-Methodology.md` before any file was touched, which is what
surfaced the badge/README staleness that became items 5-6 above.

## Final review (Phase 8's Step 15 — improvements, limitations, threats to validity, philosophy-consistent future ideas)

**Improvements made**: corpus grew from 20 to 35 files with every new
fixture serving a named, specific purpose (no padding for count); every
rule has a real sample size ≥2 now, and that sample size is visible
directly in the table instead of implied; a genuinely new diagnostic
(match-level counts) exists without touching the existing grading
contract; peak memory is now measured, not just throughput; a real,
concrete data-staleness bug was found and fixed, and — more
durably — a regression test now exists specifically to catch it recurring;
the methodology doc gained a plain-English primer, an explicit
threats-to-validity section, and a reproducibility section; and five
separate stale-number copies scattered across the repo were found and
fixed, with several converted to pointers rather than hardcoded figures
so they're structurally harder to let drift again.

**Remaining benchmark limitations** (named directly, not hedged):
35 files is still small — most rules are graded on 2-4 examples, real
statistical evidence but not strong evidence. The corpus is entirely
author-written; no independently-sourced or third-party-contributed
fixtures exist. There's no adversarial/evasion corpus — every fixture
tests realistic accidental leaks, not secrets deliberately obfuscated to
dodge this tool's specific patterns. Full match-level (planted vs.
detected vs. missed) grading was considered and deliberately not built —
the annotation-maintenance cost was judged higher than the value on top
of what file-level grading already catches; this is a real, revisitable
judgment call, not a technical impossibility.

**Remaining testing limitations**: the new
`test_committed_badge_matches_fresh_run` only checks the badge JSON
against a fresh run — it does **not** check `README.md`'s prose (the
intro line, the table, or any other doc that quotes a specific number).
Those were fixed by hand this phase but nothing stops them drifting again
after a future corpus change; a stronger version of this check (e.g.
asserting the README table's numbers parse-match a fresh run) is a real,
bounded future improvement, not implemented here because it would mean
parsing markdown tables out of prose — more fragile than it sounds for
the value added in one pass.

**Threats to validity**: see `docs/Benchmark-Methodology.md`'s own
"Threats to validity" section (construct validity, selection bias, small
per-rule N, no adversarial corpus) — written to be read directly, not
duplicated here.

**Future ideas that stay within this project's philosophy** (not
committed to, not scheduled): growing the corpus further, especially
third-party-contributed fixtures if this ever gets outside contributors
(would reduce the selection-bias limitation named above); a lightweight
historical trend log for the benchmark badge (each CI run's number
appended somewhere queryable, not just the current-state badge) to catch
slow drift a point-in-time number can't; extending the drift-detection
pattern from the badge to README's prose numbers specifically. None of
these require touching any ADR or expanding what kind of product this is.

## Current state (for orientation, not re-derivation)

```
src/dlp/          11 modules, no circular imports (see docs/Architecture.md)
docs/
  adr/0001-no-plugin-system-yet.md .. 0004-finding-fingerprint-design.md
  Limitations.md, Threat-Model.md, Architecture.md, Operations.md,
  Performance.md, Troubleshooting.md, Roadmap.md, FAQ.md, Detectors.md,
  Benchmark-Methodology.md
benchmark/
  corpus/  35 files (23 positive, 12 negative)
  run_benchmark.py (CI-gated, now with N column + match diagnostics)
  run_throughput_benchmark.py (not CI-gated, now with peak-RSS)
tests/            229 tests, 97.46% coverage, 90% CI floor
```

Zero runtime dependencies — respect it, see ADR 0002. `tomllib`/
`hypothesis`/`pytest-cov`/`ruff`/`mypy` are dev-only.

## Known issues / gaps still open

- Same short list as before, unchanged since Phase 4: `scanner.py:90,121,
  192-201`, `github_pr.py:231-232`, `cli.py:306` — pre-existing or
  process-boundary coverage gaps, none tied to a real bug.
- CI itself has not been run (nothing pushed).
- `v0.1.0` is still the only tag — everything in Phases 1-8 is
  `[Unreleased]`.
- `Finding.fingerprint`'s short-secret collision case — see
  [ADR 0004](docs/adr/0004-finding-fingerprint-design.md)'s Consequences.
- **New**: the badge-drift test only covers `.github/badges/benchmark.json`,
  not README's prose numbers — see "Remaining testing limitations" above.

## Open questions for the human

- **Push Phases 1-8 now for real CI validation?** The case hasn't gotten
  weaker — everything is gated, benchmark-verified, and this phase in
  particular found and fixed a real bug (badge/README drift) that only
  exists *because* nothing's been pushed yet, which is its own argument
  for pushing sooner.
- **Is `[tool.dlp]` config support something you want dog-fooded in this
  repo's own `pyproject.toml`**, or "built and tested, not self-adopted"
  long-term? Still open.
- **Extend the drift-detection pattern to README's prose numbers?** Named
  as a real, bounded future improvement above — not started.
- **The platform-scale rebuild request from three phases ago** — still
  declined by default per every relevant ADR.

## Potential risks if continuing unattended

- None — everything through Phase 8 has been gated and benchmark-verified
  with no regressions, and follows the same evidence-over-claims standard
  it asked the benchmark itself to meet.
