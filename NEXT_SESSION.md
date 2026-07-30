# Handoff — engineering transformation, in progress

**Last updated:** 2026-07-30, end of the session that completed Phase 2.
**Read this file first** if you're picking this work up cold — it should let
you continue without re-deriving anything below.

## What this is

`dlp-secret-pii-scanner` is going through a structured engineering-quality
pass: audit → 5-phase roadmap → incremental, individually-verified PRs, each
with its own Goal/Reasoning/Tradeoffs writeup in its commit message. Nothing
has been pushed to `origin` or merged — everything lives on two local
branches, one commit per coherent change, matching how this repo already
holds PR merges for an explicit human go-ahead.

## Completed work

### Phase 1 — Quick wins (branch `engineering-audit/phase-1-quick-wins`, 5 commits)
1. `6552c88` — `CONTRIBUTING.md`
2. `9a58a85` — `CHANGELOG.md`, backfilled from git history
3. `7c6d026` — 3 tailored issue forms, PR template, `CODEOWNERS`
4. `3435130` — `--version`, `python -m dlp`, worked `--help` examples
5. `7d73713` — CHANGELOG catch-up for #3/#4

### Phase 2 — Engineering improvements (branch `engineering-audit/phase-2-engineering-improvements`, stacked on Phase 1, 5 commits)
1. `9ec4343` — `ruff check` + `mypy src/` (strict) + 90% coverage floor, all as CI gates. `py.typed` added (PEP 561). 5 real lint findings and 5 real type gaps fixed, not just config-wiring.
2. `d6d9a3c` — Fixed two silent-failure paths (`scan_file`'s `except OSError` and >5MB skip both returned `[]`, indistinguishable from a clean scan). Added `ScanStats`, threaded optionally through `scan_file`/`scan_paths`, CLI prints a stderr summary only when something was actually skipped.
3. `c9cd3c4` — `dlp.github_pr.post_review_comments` was unbounded and re-raised any rate-limit error uncaught. Now capped at 25 comments (highest severity kept), retries a detected GitHub rate limit with backoff, never retries a real permissions error.
4. `f6d685c` — Hypothesis property tests for Luhn/SSN/entropy. Found and fixed a real bug along the way: `.hypothesis`'s cache dir wasn't in `DEFAULT_SKIP_DIRS`, so self-scanning flagged the tool's own test cache as secrets.
5. `14b62fd` — `pyproject.toml [tool.dlp]` per-project config support, via stdlib `tomllib` (zero new runtime dependency; documented no-op on Python 3.10). CLI flags always win; `--no-config` opts out.

**Net across both phases:** 130 → 200 tests, coverage 96.45% → 97.98%, three real
operational-trust bugs fixed (silent skip, unbounded PR-comment loop,
self-inflicted cache-dir noise), zero regressions. Every commit individually
verified against the full local gate sequence (ruff, mypy, pytest+coverage,
benchmark, self-scan, 10k-iteration fuzz) before landing — see each commit
message for its own Problem/Root cause/Engineering decision/Tradeoffs writeup.

## Current architecture (for orientation, not re-derivation)

```
src/dlp/
  cli.py            argparse entry point, thin orchestration only
  config.py         [NEW] pyproject.toml [tool.dlp] loading/validation
  scanner.py        file walk + Finding dataclass + ScanStats [NEW]
  detectors.py       11 regex detectors + Shannon-entropy detector
  report.py          table/json/sarif rendering
  baseline.py         fingerprint-based suppression
  diff.py             git diff --name-only wrapper for --diff-only
  ignore.py            .dlpignore + inline # dlp-ignore
  github_pr.py        inline PR comments, now rate-limit-aware [CHANGED]
  shared_finding.py    maps onto the ecosystem-wide finding schema
scripts/coverage_badge.py   [NEW] mirrors run_benchmark.py's badge pattern
```

Zero runtime dependencies is a load-bearing, deliberate constraint across the
whole codebase — respect it. `config.py`'s `tomllib` and everything test-only
(`hypothesis`, `pytest-cov`, `ruff`, `mypy`) are dev-only, not runtime.

## Known issues / gaps still open

- **Pre-existing, low-priority, not tied to a real bug:** `scanner.py:89,120`
  (the `ignore_root`-fallback path and the truly-empty-file early return),
  `github_pr.py:231-232` (`main()`'s "no findings" early return). None are
  security- or correctness-relevant; skip unless doing a dedicated coverage pass.
- CI itself has not been run (nothing pushed) — everything above is verified
  *locally* against the exact commands CI runs, not by CI itself. First push
  should be watched closely for anything environment-specific that differs
  from this sandbox.
- This repo's own `pyproject.toml` deliberately has no `[tool.dlp]` section —
  see commit `14b62fd`'s message for why (would silently change dozens of
  existing tests' effective defaults, since they run with cwd at repo root).

## Recommended next task: Phase 3, item 1 — ADR for the plugin-system decision

**Why this one first:** documentation-only, zero code risk, and it's the one
Phase 3 item explicitly flagged as depending on nothing else. The audit's
Maintainability section names `detectors.REGEX_DETECTORS` as a hardcoded
list — the one real extensibility seam in an otherwise very low-coupling
codebase — and recommends writing down *why* a plugin/entry-point system was
deliberately deferred rather than letting it look like an oversight to a
reviewer. Write `docs/adr/0001-no-plugin-system-yet.md` (Context/Problem/
Alternatives/Decision/Consequences/Tradeoffs format, per the original audit
request) covering: current cost of adding a detector (edit `detectors.py`,
cut a release) vs. the cost of a plugin ABI (versioning, discovery, trust
boundary for third-party code running against real repos) vs. staying as-is
given the rule set's actual size (11 rules, ~200 lines, added-to maybe once
a quarter per the git history).

**Estimated effort:** 1 hour. **Risk:** none (pure documentation).

## Suggested implementation order after that

Phase 3 (architecture, needs the ADR above to inform them):
1. ADR above (~1hr, no risk) — do first
2. `--jobs` parallel scanning via `ThreadPoolExecutor`/`ProcessPoolExecutor` (~3-4hrs, medium risk — touches the hot path, needs a throughput benchmark to justify which pool type)
3. Throughput benchmark (files/sec, MB/sec) added to `benchmark/` (~2hrs) — do *before* or alongside #2, not after, so the parallelism change has something to measure against
4. Structured `logging` adoption + `--verbose`/`--quiet` (~2hrs) — natural follow-on to the ScanStats/stderr work already done in Phase 2

Phase 4 (docs: Architecture.md, Threat-Model.md, Operations.md, Troubleshooting.md,
Performance.md, Limitations.md) and Phase 5 (Design-Decisions.md, FAQ.md, Roadmap.md,
Development-Log.md, Case-Study.md, retroactive ADRs for zero-deps/regex-vs-ML/
fingerprint-design) are still fully open — see the original audit's roadmap
table (in this conversation's history, not yet its own committed file) for
full effort/ROI estimates per item.

## Open questions for the human

- Push Phase 1+2 now for real CI validation, or keep accumulating locally
  through Phase 3? Recommend pushing once Phase 3's parallel-scanning change
  lands, since that's the first change in this pass with any real behavioral
  risk (everything so far has been additive/config/test).
- Is `[tool.dlp]` config support (Phase 2, item 6) something you actually
  want dog-fooded in this repo's own `pyproject.toml`, or is "built and
  tested, not self-adopted" the right call long-term too?

## Potential risks if continuing unattended

- `--jobs` parallel scanning is the first Phase 3+ item that touches
  `scan_paths`' actual hot path rather than adding around it — worth extra
  scrutiny on ordering guarantees (findings currently come back in a stable,
  deterministic order; a naive thread pool `.map()` could reorder them,
  which would silently break any test or downstream consumer relying on
  order, e.g. the benchmark's `(file, rule)` pairing).
- None of the remaining Phase 3/4/5 items are destructive or touch CI
  trust boundaries the way Phase 2's `github_pr.py` work did — lower
  supervision needed than Phase 2 required.
